from __future__ import annotations

import re
from typing import Any

from .models import Job, MatchScore
from .query import clean_role, meaningful_terms


DEFAULT_WEIGHTS = {
    "role_fit": 25,
    "skill_fit": 25,
    "experience_fit": 15,
    "education_fit": 10,
    "location_fit": 8,
    "availability_fit": 5,
    "industry_fit": 5,
    "compensation_fit": 4,
    "company_preference_fit": 3,
}

DEGREE_RANK = {"不限": 0, "中专": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}


def _ratio(points: float, maximum: float) -> float:
    return max(0.0, min(1.0, points / maximum if maximum else 1.0))


def _role_fit(profile: dict[str, Any], job: Job) -> tuple[float, list[str]]:
    roles = profile.get("target", {}).get("primary_roles", []) + profile.get("target", {}).get("secondary_roles", [])
    title = job.title.lower()
    matched: list[str] = []
    best = 0.0
    for raw_role in roles:
        role = clean_role(str(raw_role))
        compact = re.sub(r"\s+", "", role.lower())
        compact_title = re.sub(r"\s+", "", title)
        if compact and compact in compact_title:
            return 1.0, [role]
        terms = meaningful_terms(role)
        hits = [term for term in terms if term.lower() in title]
        if "算法" in role and "算法" in job.title and "算法" not in hits:
            hits.append("算法")
        score = len(hits) / max(1, min(3, len(terms)))
        if score > best:
            best, matched = min(1.0, score), hits
    return best, matched


def _skill_fit(profile: dict[str, Any], job: Job) -> tuple[float, list[str], list[str]]:
    skills = [str(item.get("name", "")) for item in profile.get("capabilities", {}).get("skills", [])]
    skills = [skill for skill in skills if skill]
    text = job.searchable_text()
    matched = [skill for skill in skills if skill.lower() in text]
    important = skills[:12]
    missing = [skill for skill in important if skill not in matched]
    if not skills:
        return 1.0, [], []
    return min(1.0, len(matched) / max(3, min(8, len(skills)))), matched, missing


def _experience_fit(profile: dict[str, Any], job: Job) -> float:
    if job.employment_type in {"internship", "campus"}:
        return 1.0
    requirement = job.experience or ""
    if not requirement or "不限" in requirement or "应届" in requirement:
        return 1.0
    numbers = [int(value) for value in re.findall(r"(\d+)\s*年", requirement)]
    if not numbers:
        return 0.75
    candidate_years = float(profile.get("career", {}).get("experience_months") or 0) / 12
    minimum = min(numbers)
    if candidate_years >= minimum:
        return 1.0
    return 0.5 if candidate_years + 1 >= minimum else 0.0


def _education_fit(profile: dict[str, Any], job: Job) -> float:
    required = job.education
    candidate = profile.get("career", {}).get("highest_degree")
    if not required or not candidate or "不限" in required:
        return 1.0
    required_rank = max((rank for degree, rank in DEGREE_RANK.items() if degree in required), default=0)
    candidate_rank = DEGREE_RANK.get(str(candidate), 0)
    return 1.0 if candidate_rank >= required_rank else 0.0


def _location_fit(profile: dict[str, Any], job: Job) -> float:
    target = profile.get("target", {})
    preferred = [str(x) for x in target.get("preferred_locations", [])]
    acceptable = [str(x) for x in target.get("acceptable_locations", [])]
    if not preferred and not acceptable:
        return 1.0
    text = " ".join(job.locations)
    if any(city in text for city in preferred):
        return 1.0
    if any(city in text for city in acceptable):
        return 0.75
    if "全国" in text or "远程" in text:
        return 0.65
    return 0.0


def _industry_fit(profile: dict[str, Any], job: Job) -> float:
    preferred = [str(x).lower() for x in profile.get("target", {}).get("preferred_industries", [])]
    excluded = [str(x).lower() for x in profile.get("target", {}).get("excluded_industries", [])]
    text = (job.industry or "").lower()
    if any(value and value in text for value in excluded):
        return 0.0
    if not preferred:
        return 1.0
    return 1.0 if any(value in text for value in preferred) else 0.4


def _compensation_fit(profile: dict[str, Any], job: Job) -> float:
    salary = profile.get("target", {}).get("salary", {})
    minimum = salary.get("monthly_min_cny")
    if not minimum or job.salary_period != "month" or job.salary_max is None:
        return 1.0
    if job.salary_max >= minimum:
        return 1.0
    return _ratio(job.salary_max, float(minimum))


def score_job(profile: dict[str, Any], job: Job) -> MatchScore:
    configured = profile.get("matching_config", {}).get("weights", {})
    weights = {**DEFAULT_WEIGHTS, **{k: v for k, v in configured.items() if isinstance(v, (int, float))}}
    role_ratio, role_terms = _role_fit(profile, job)
    skill_ratio, matched_skills, missing_skills = _skill_fit(profile, job)
    ratios = {
        "role_fit": role_ratio,
        "skill_fit": skill_ratio,
        "experience_fit": _experience_fit(profile, job),
        "education_fit": _education_fit(profile, job),
        "location_fit": _location_fit(profile, job),
        "availability_fit": 1.0,
        "industry_fit": _industry_fit(profile, job),
        "compensation_fit": _compensation_fit(profile, job),
        "company_preference_fit": 1.0,
    }
    breakdown = {key: round(weights.get(key, 0) * value, 2) for key, value in ratios.items()}
    total_weight = sum(float(weights.get(key, 0)) for key in ratios) or 100
    total = round(sum(breakdown.values()) * 100 / total_weight, 1)

    config = profile.get("matching_config", {})
    text = job.searchable_text()
    excluded = [str(x) for x in config.get("excluded_keywords", []) if str(x).strip()]
    excluded += [str(x) for x in profile.get("constraints", {}).get("deal_breakers", []) if str(x).strip()]
    must_have = [str(x) for x in config.get("must_have_keywords", []) if str(x).strip()]
    blocked = [keyword for keyword in excluded if keyword.lower() in text]
    missing_must = [keyword for keyword in must_have if keyword.lower() not in text]
    hard_pass = not blocked and not missing_must
    if not hard_pass:
        total = min(total, 39.0)

    reasons: list[str] = []
    if role_terms:
        reasons.append("岗位方向命中：" + "、".join(role_terms[:4]))
    if matched_skills:
        reasons.append("技能命中：" + "、".join(matched_skills[:8]))
    if job.locations and ratios["location_fit"] >= 0.75:
        reasons.append("地点符合画像偏好")
    warnings: list[str] = []
    if blocked:
        warnings.append("命中排除条件：" + "、".join(blocked))
    if missing_must:
        warnings.append("缺少必备关键词：" + "、".join(missing_must))
    if not job.requirements and not job.description:
        warnings.append("渠道未提供完整岗位描述，技能分可能偏低")

    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"
    nice = [str(x) for x in config.get("nice_to_have_keywords", []) if str(x).lower() in text]
    return MatchScore(
        total=total,
        grade=grade,
        hard_constraints_passed=hard_pass,
        breakdown=breakdown,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        matched_keywords=role_terms + nice,
        reasons=reasons,
        warnings=warnings,
    )
