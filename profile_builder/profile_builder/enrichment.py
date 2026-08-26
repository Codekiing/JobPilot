from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Protocol

from .completion import calculate_completion
from .models import UserProfile
from .taxonomy import infer_skills
from .utils import get_path, is_present, set_path


KNOWN_CITIES = (
    "北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉", "苏州", "西安", "重庆", "长沙",
    "天津", "青岛", "厦门", "东莞", "佛山", "香港", "澳门", "新加坡", "东京", "伦敦", "纽约", "旧金山",
)


FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "career.career_stage": str,
    "career.job_search_status": str,
    "career.current_city": str,
    "career.highest_degree": str,
    "career.graduation_date": str,
    "target.employment_types": list,
    "target.primary_roles": list,
    "target.secondary_roles": list,
    "target.preferred_industries": list,
    "target.excluded_industries": list,
    "target.preferred_locations": list,
    "target.acceptable_locations": list,
    "target.work_modes": list,
    "target.available_from": str,
    "target.salary.monthly_min_cny": int,
    "target.salary.monthly_max_cny": int,
    "target.salary.expected_salary_months": int,
    "target.salary.negotiable": bool,
    "target.internship.days_per_week": int,
    "target.internship.duration_months": int,
    "target.internship.conversion_intent": str,
    "capabilities.user_confirmed_strengths": list,
    "capabilities.languages": list,
    "preferences.company_sizes": list,
    "preferences.company_stages": list,
    "preferences.business_domains": list,
    "preferences.culture_keywords": list,
    "constraints.relocation": bool,
    "constraints.travel_frequency": str,
    "constraints.work_authorization": list,
    "constraints.overtime_preference": str,
    "constraints.deal_breakers": list,
    "matching_config.must_have_keywords": list,
    "matching_config.nice_to_have_keywords": list,
    "matching_config.excluded_keywords": list,
}

MODEL_ENUMS: dict[str, set[str]] = {
    "career.career_stage": {"student", "new_graduate", "experienced", "career_switcher"},
    "career.job_search_status": {"actively_looking", "open_to_opportunities", "interviewing", "offer_received", "not_looking"},
    "target.internship.conversion_intent": {"yes", "no", "negotiable"},
    "constraints.travel_frequency": {"none", "occasional", "regular", "any"},
    "constraints.overtime_preference": {"low", "moderate", "high", "any"},
}


class ModelEnricher(Protocol):
    model: str

    def extract_patches(self, profile: UserProfile, survey_answers: dict[str, str]) -> list[dict[str, Any]]:
        ...


class ProfileEnricher:
    """Apply transparent rules first, then optional model patches to missing fields."""

    def enrich(
        self,
        profile: UserProfile,
        survey_answers: dict[str, str],
        *,
        model_enricher: ModelEnricher | None = None,
    ) -> UserProfile:
        data = profile.to_dict()
        now = datetime.now(timezone.utc).isoformat()
        data["questionnaire"]["survey_answers"] = {
            question_id: {"value": answer, "answered_at": now, "source": "user"}
            for question_id, answer in survey_answers.items()
            if str(answer).strip()
        }
        rule_changes = self._apply_rules(data, survey_answers)
        data["questionnaire"]["rule_enrichment"] = {
            "applied_at": now,
            "changed_fields": rule_changes,
        }

        if model_enricher is not None:
            interim = UserProfile.from_dict(data)
            patches = model_enricher.extract_patches(interim, survey_answers)
            applied = self._apply_model_patches(data, patches)
            data["questionnaire"]["model_enrichment"] = {
                "model": model_enricher.model,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "applied_patches": applied,
            }

        updated = UserProfile.from_dict(data)
        updated.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated.questionnaire["last_session_at"] = updated.metadata["updated_at"]
        updated.completion = calculate_completion(updated)
        return updated

    def _apply_rules(self, data: dict[str, Any], answers: dict[str, str]) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for question_id, raw_answer in answers.items():
            answer = str(raw_answer).strip()
            if not answer:
                continue
            handler = getattr(self, f"_rule_{question_id}", None)
            if handler:
                handler(data, answer, changes)
        return changes

    def _set(self, data: dict[str, Any], path: str, value: Any, changes: list[dict[str, Any]], *, overwrite: bool = True) -> None:
        if not is_present(value):
            return
        previous = get_path(data, path)
        if not overwrite and is_present(previous):
            return
        if previous == value:
            return
        set_path(data, path, value)
        changes.append({"path": path, "value": value, "source": "rule"})

    def _rule_basic_status(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        name = re.search(r"(?:姓名|我叫)\s*[：:]?\s*([\u4e00-\u9fff·]{2,8})", answer)
        if name:
            self._set(data, "identity.name", name.group(1), changes)
        email = re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", answer, re.IGNORECASE)
        if email:
            self._set(data, "identity.contact.email", email.group(0), changes)
        phone = re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", answer)
        if phone:
            self._set(data, "identity.contact.phone", phone.group(0), changes)
        cities = _find_cities(answer)
        if cities:
            self._set(data, "career.current_city", cities[0], changes)
        stage = None
        if re.search(r"在校|学生|在读", answer):
            stage = "student"
        elif re.search(r"应届", answer):
            stage = "new_graduate"
        elif re.search(r"转行", answer):
            stage = "career_switcher"
        elif re.search(r"社招|工作经验|在职", answer):
            stage = "experienced"
        if stage:
            self._set(data, "career.career_stage", stage, changes)
        graduation = re.search(r"(20\d{2})\s*届", answer)
        if graduation:
            self._set(data, "career.graduation_date", f"{graduation.group(1)}-06", changes, overwrite=False)
        statuses = (
            (r"积极|急招|尽快找|正在找", "actively_looking"),
            (r"面试中|正在面试", "interviewing"),
            (r"已有\s*offer|拿到\s*offer", "offer_received"),
            (r"看看机会|关注机会|随缘", "open_to_opportunities"),
            (r"暂不|不找工作", "not_looking"),
        )
        for pattern, value in statuses:
            if re.search(pattern, answer, re.IGNORECASE):
                self._set(data, "career.job_search_status", value, changes)
                break

    def _rule_job_targets(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        employment: list[str] = []
        for pattern, value in ((r"全职|校招", "full_time"), (r"实习", "internship"), (r"兼职", "part_time"), (r"合同", "contract")):
            if re.search(pattern, answer):
                employment.append(value)
        if employment:
            self._set(data, "target.employment_types", employment, changes)
        fragments = _split_values(answer)
        roles = [
            re.sub(r"^(?:首选|其次|备选|全职|实习)\s*[：:]?\s*", "", value).strip()
            for value in fragments
            if re.search(r"工程师|科学家|研究员|开发|算法|产品|运营|设计|岗位", value)
        ]
        roles = [role for role in roles if role and role not in {"全职", "实习"}]
        if roles:
            self._set(data, "target.primary_roles", roles[:1], changes)
            if len(roles) > 1:
                self._set(data, "target.secondary_roles", roles[1:], changes)

    def _rule_location_work_mode(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        preferred_part = re.split(r"可接受|其次|备选", answer, maxsplit=1)[0]
        preferred = _find_cities(preferred_part)
        all_cities = _find_cities(answer)
        acceptable = [city for city in all_cities if city not in preferred]
        if preferred:
            self._set(data, "target.preferred_locations", preferred, changes)
        if acceptable:
            self._set(data, "target.acceptable_locations", acceptable, changes)
        work_modes: list[str] = []
        for pattern, value in ((r"现场|坐班|线下", "onsite"), (r"混合", "hybrid"), (r"远程", "remote")):
            if re.search(pattern, answer):
                work_modes.append(value)
        if work_modes:
            self._set(data, "target.work_modes", work_modes, changes)
        if re.search(r"不(?:接受|考虑)?搬迁|不异地", answer):
            self._set(data, "constraints.relocation", False, changes)
        elif re.search(r"接受搬迁|可以搬迁|可异地", answer):
            self._set(data, "constraints.relocation", True, changes)

    def _rule_availability(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        full_date = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", answer)
        month_date = re.search(r"(20\d{2})[-/.年](\d{1,2})月?", answer)
        if full_date:
            candidate = f"{int(full_date.group(1)):04d}-{int(full_date.group(2)):02d}-{int(full_date.group(3)):02d}"
            if _is_valid_date(candidate):
                self._set(data, "target.available_from", candidate, changes)
        elif month_date:
            candidate = f"{int(month_date.group(1)):04d}-{int(month_date.group(2)):02d}-01"
            if _is_valid_date(candidate):
                self._set(data, "target.available_from", candidate, changes)
        elif re.search(r"随时|立即", answer):
            self._set(data, "target.available_from", date.today().isoformat(), changes)
        days = re.search(r"每周\s*(\d)\s*天", answer)
        if days and 1 <= int(days.group(1)) <= 7:
            self._set(data, "target.internship.days_per_week", int(days.group(1)), changes)
        months = re.search(r"(?:连续|实习|持续)\s*(\d{1,2})\s*个?月", answer)
        if months:
            self._set(data, "target.internship.duration_months", int(months.group(1)), changes)
        if re.search(r"不(?:考虑|希望)?转正", answer):
            self._set(data, "target.internship.conversion_intent", "no", changes)
        elif re.search(r"希望转正|可转正|转正意愿", answer):
            self._set(data, "target.internship.conversion_intent", "yes", changes)

    def _rule_compensation(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        values = [_salary_to_cny(number, unit) for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([kK千万元]?)", answer)]
        values = [value for value in values if 1000 <= value <= 1_000_000]
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*([kK千万元]?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*([kK千万元]?)", answer)
        minimum_match = re.search(r"最低[^\d]*(\d+(?:\.\d+)?)\s*([kK千万元]?)", answer)
        if range_match:
            minimum = (
                _salary_to_cny(minimum_match.group(1), minimum_match.group(2))
                if minimum_match
                else _salary_to_cny(range_match.group(1), range_match.group(2) or range_match.group(4))
            )
            maximum = _salary_to_cny(range_match.group(3), range_match.group(4) or range_match.group(2))
            self._set(data, "target.salary.monthly_min_cny", minimum, changes)
            if maximum >= minimum:
                self._set(data, "target.salary.monthly_max_cny", maximum, changes)
        elif values:
            if minimum_match:
                self._set(data, "target.salary.monthly_min_cny", _salary_to_cny(minimum_match.group(1), minimum_match.group(2)), changes)
            else:
                self._set(data, "target.salary.monthly_min_cny", min(values), changes)
            if len(values) > 1:
                self._set(data, "target.salary.monthly_max_cny", max(values), changes)
        salary_months = re.search(r"(\d{2})\s*薪", answer)
        if salary_months and 12 <= int(salary_months.group(1)) <= 24:
            self._set(data, "target.salary.expected_salary_months", int(salary_months.group(1)), changes)
        if re.search(r"不可商议|不议价", answer):
            self._set(data, "target.salary.negotiable", False, changes)
        elif re.search(r"可商议|可谈|面议", answer):
            self._set(data, "target.salary.negotiable", True, changes)

    def _rule_strengths_skills(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        strengths = _split_values(answer)
        if strengths:
            self._set(data, "capabilities.user_confirmed_strengths", strengths, changes)
        inferred = infer_skills([{"order": "survey", "content": answer}])
        existing = list(get_path(data, "capabilities.skills", []) or [])
        names = {item.get("name") for item in existing}
        for skill in inferred:
            if skill["name"] in names:
                continue
            skill["source"] = "user_survey"
            skill["evidence_refs"] = ["survey:strengths_skills"]
            existing.append(skill)
        if inferred:
            self._set(data, "capabilities.skills", existing, changes)

    def _rule_achievements(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        highlights = _split_values(answer)
        if highlights:
            self._set(data, "evidence.user_highlights", highlights, changes)

    def _rule_company_industry(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        sizes: list[str] = []
        for pattern, value in ((r"初创|创业", "startup"), (r"中小", "small_medium"), (r"大型|大厂|大中型", "large"), (r"不限规模", "any")):
            if re.search(pattern, answer):
                sizes.append(value)
        if sizes:
            self._set(data, "preferences.company_sizes", sizes, changes)
        stages: list[str] = []
        for pattern, value in ((r"早期|未融资", "early"), (r"成长|成长期", "growth"), (r"成熟", "mature"), (r"上市", "listed"), (r"阶段不限", "any")):
            if re.search(pattern, answer):
                stages.append(value)
        if stages:
            self._set(data, "preferences.company_stages", stages, changes)
        domains = [value for value in _split_values(answer) if re.search(r"AI|人工智能|大模型|互联网|金融|游戏|医疗|制造|企业服务|基础设施|电商", value, re.IGNORECASE)]
        preferred = [value for value in domains if not re.search(r"不考虑|排除|不要", value)]
        excluded = [re.sub(r".*(?:不考虑|排除|不要)\s*", "", value) for value in domains if re.search(r"不考虑|排除|不要", value)]
        if preferred:
            self._set(data, "preferences.business_domains", preferred, changes)
            self._set(data, "target.preferred_industries", preferred, changes, overwrite=False)
        if excluded:
            self._set(data, "target.excluded_industries", excluded, changes)

    def _rule_constraints(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        if re.search(r"不出差|拒绝出差", answer):
            self._set(data, "constraints.travel_frequency", "none", changes)
        elif re.search(r"不接受(?:长期|经常)出差", answer):
            self._set(data, "constraints.travel_frequency", "occasional", changes)
        elif re.search(r"偶尔出差|少量出差", answer):
            self._set(data, "constraints.travel_frequency", "occasional", changes)
        elif re.search(r"经常出差|长期出差", answer):
            self._set(data, "constraints.travel_frequency", "regular", changes)
        if re.search(r"不加班|低强度", answer):
            self._set(data, "constraints.overtime_preference", "low", changes)
        elif re.search(r"适度加班|偶尔加班", answer):
            self._set(data, "constraints.overtime_preference", "moderate", changes)
        elif re.search(r"高强度|接受加班", answer):
            self._set(data, "constraints.overtime_preference", "high", changes)
        blockers = [value for value in _split_values(answer) if re.search(r"不接受|拒绝|不能|不要|单休|无社保", value)]
        if blockers:
            self._set(data, "constraints.deal_breakers", blockers, changes)

    def _rule_languages_authorization(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        language_parts = [value for value in _split_values(answer) if re.search(r"中文|英语|英文|日语|法语|德语|粤语|普通话|母语|雅思|托福", value)]
        if language_parts:
            self._set(data, "capabilities.languages", language_parts, changes)
        authorization = []
        for region in ("中国大陆", "香港", "澳门", "台湾", "新加坡", "美国", "英国", "欧盟", "日本", "加拿大", "澳大利亚"):
            if region in answer:
                authorization.append(region)
        if authorization:
            self._set(data, "constraints.work_authorization", authorization, changes)

    def _rule_matching_keywords(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        labels = (
            ("must_have_keywords", r"必须\s*[：:]\s*([^；;]+)"),
            ("nice_to_have_keywords", r"(?:加分|优先)\s*[：:]\s*([^；;]+)"),
            ("excluded_keywords", r"(?:排除|不要)\s*[：:]\s*([^；;]+)"),
        )
        matched = False
        for field, pattern in labels:
            match = re.search(pattern, answer)
            if match:
                matched = True
                self._set(data, f"matching_config.{field}", _split_values(match.group(1)), changes)
        if not matched:
            self._set(data, "matching_config.nice_to_have_keywords", _split_values(answer), changes)

    def _rule_additional_context(self, data: dict[str, Any], answer: str, changes: list[dict[str, Any]]) -> None:
        self._set(data, "questionnaire.additional_context", answer, changes)

    def _apply_model_patches(self, data: dict[str, Any], patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for patch in patches:
            path = str(patch.get("path", ""))
            value = patch.get("value")
            expected_type = FIELD_TYPES.get(path)
            if expected_type is None or not isinstance(value, expected_type) or not _valid_model_value(path, value):
                continue
            # A model may complete missing information, but cannot overwrite a
            # reliable resume- or rule-derived value.
            if is_present(get_path(data, path)):
                continue
            set_path(data, path, value)
            applied.append(
                {
                    "path": path,
                    "value": value,
                    "confidence": patch.get("confidence"),
                    "evidence_answer_ids": patch.get("evidence_answer_ids", []),
                    "source": "model",
                }
            )
        return applied


def _find_cities(text: str) -> list[str]:
    found = [(text.find(city), city) for city in KNOWN_CITIES if city in text]
    return [city for _, city in sorted(found)]


def _split_values(text: str) -> list[str]:
    values = [value.strip(" .。") for value in re.split(r"[,，、；;\n]", text) if value.strip(" .。")]
    return list(dict.fromkeys(values))


def _salary_to_cny(number: str, unit: str) -> int:
    value = float(number)
    multiplier = 1
    if unit in {"k", "K", "千"}:
        multiplier = 1_000
    elif unit == "万":
        multiplier = 10_000
    return round(value * multiplier)


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _valid_model_value(path: str, value: Any) -> bool:
    if path in MODEL_ENUMS and value not in MODEL_ENUMS[path]:
        return False
    if path == "target.available_from" and not _is_valid_date(value):
        return False
    if path == "career.graduation_date":
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError:
            return False
    limits = {
        "target.internship.days_per_week": (1, 7),
        "target.internship.duration_months": (1, 36),
        "target.salary.expected_salary_months": (1, 24),
        "target.salary.monthly_min_cny": (0, 1_000_000),
        "target.salary.monthly_max_cny": (0, 1_000_000),
    }
    if path in limits:
        minimum, maximum = limits[path]
        return minimum <= value <= maximum
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
    return True
