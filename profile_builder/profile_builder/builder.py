from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .completion import calculate_completion
from .models import UserProfile
from .taxonomy import infer_skills


DEGREE_ORDER = {"博士": 5, "硕士": 4, "本科": 3, "学士": 3, "大专": 2, "高中": 1}


class ProfileBuilder:
    """Build a deterministic job-matching profile from component-one JSON."""

    def load_resume(self, path: str | Path) -> dict[str, Any]:
        resume_path = Path(path).expanduser().resolve()
        if not resume_path.is_file():
            raise FileNotFoundError(f"第一组件输出不存在: {resume_path}")
        with resume_path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        required = {"source", "profile", "sections", "raw_text"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"不是有效的第一组件输出，缺少: {', '.join(sorted(missing))}")
        return value

    def build_from_file(self, path: str | Path) -> UserProfile:
        resume_path = Path(path).expanduser().resolve()
        return self.build(self.load_resume(resume_path), resume_path=resume_path)

    def build(self, resume: dict[str, Any], *, resume_path: Path | None = None) -> UserProfile:
        source = resume.get("source", {})
        resume_sha = str(source.get("sha256") or _json_sha256(resume))
        profile_id = f"profile-{resume_sha[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        sections = list(resume.get("sections", []))
        raw_text = str(resume.get("raw_text", ""))
        resume_profile = dict(resume.get("profile", {}))

        education_sections = [section for section in sections if section.get("type") == "education"]
        highest_degree = _infer_highest_degree(education_sections)
        graduation_date = _infer_graduation_date(education_sections)
        career_stage = _infer_career_stage(raw_text, graduation_date)
        job_intention = str(resume_profile.get("job_intention") or "").strip()
        primary_roles = [_clean_target_role(job_intention)] if job_intention else []
        primary_roles = [role for role in primary_roles if role]
        employment_types = _infer_employment_types(raw_text, career_stage)
        evidence_sections = _build_evidence_sections(sections)

        profile = UserProfile(
            schema_version="1.0",
            profile_id=profile_id,
            metadata={
                "component": "profile_builder",
                "component_version": "0.1.0",
                "created_at": now,
                "updated_at": now,
                "source_resume_json": str(resume_path) if resume_path else None,
                "source_resume_sha256": resume_sha,
                "inference_policy": "deterministic_local_v1",
            },
            identity={
                "name": resume_profile.get("name"),
                "contact": {
                    "email": resume_profile.get("email"),
                    "phone": resume_profile.get("phone"),
                    "links": resume_profile.get("links", []),
                },
            },
            career={
                "career_stage": career_stage,
                "job_search_status": None,
                "current_city": resume_profile.get("location"),
                "highest_degree": highest_degree,
                "graduation_date": graduation_date,
                "experience_months": _calculate_experience_months(sections),
            },
            target={
                "employment_types": employment_types,
                "primary_roles": primary_roles,
                "secondary_roles": [],
                "preferred_industries": [],
                "excluded_industries": [],
                "preferred_locations": [],
                "acceptable_locations": [],
                "work_modes": [],
                "available_from": None,
                "salary": {
                    "monthly_min_cny": None,
                    "monthly_max_cny": None,
                    "expected_salary_months": None,
                    "negotiable": True,
                },
                "internship": {
                    "days_per_week": None,
                    "duration_months": None,
                    "conversion_intent": None,
                },
            },
            capabilities={
                "skills": infer_skills(sections),
                "user_confirmed_strengths": [],
                "languages": [],
            },
            evidence={
                "resume_sections": evidence_sections,
                "education": _section_items(sections, {"education"}),
                "experience": _section_items(sections, {"experience", "internship"}),
                "projects": _section_items(sections, {"project", "research", "open_source"}),
                "publications": _section_items(sections, {"publications"}),
                "awards": _section_items(sections, {"awards", "certifications"}),
                "quantified_achievements": _extract_quantified_achievements(sections),
            },
            preferences={
                "company_sizes": [],
                "company_stages": [],
                "business_domains": [],
                "culture_keywords": [],
            },
            constraints={
                "relocation": None,
                "travel_frequency": None,
                "work_authorization": [],
                "overtime_preference": None,
                "deal_breakers": [],
            },
            matching_config={
                "must_have_keywords": [],
                "nice_to_have_keywords": [],
                "excluded_keywords": [],
                "weights": {
                    "role_fit": 25,
                    "skill_fit": 25,
                    "experience_fit": 15,
                    "education_fit": 10,
                    "location_fit": 8,
                    "availability_fit": 5,
                    "industry_fit": 5,
                    "compensation_fit": 4,
                    "company_preference_fit": 3,
                },
            },
            questionnaire={
                "answers": {},
                "skipped_question_ids": [],
                "last_session_at": None,
            },
        )
        profile.completion = calculate_completion(profile)
        return profile


def _infer_highest_degree(sections: list[dict[str, Any]]) -> str | None:
    best: tuple[int, str] | None = None
    text = "\n".join(str(section.get("content", "")) for section in sections)
    for degree, rank in DEGREE_ORDER.items():
        if degree in text and (best is None or rank > best[0]):
            normalized = {"学士": "本科"}.get(degree, degree)
            best = rank, normalized
    return best[1] if best else None


def _infer_graduation_date(sections: list[dict[str, Any]]) -> str | None:
    candidates: list[tuple[int, int]] = []
    for section in sections:
        for item in section.get("items", []):
            date_range = str(item.get("date") or "")
            matches = re.findall(r"((?:19|20)\d{2})[./年-](\d{1,2})", date_range)
            if matches:
                year, month = matches[-1]
                candidates.append((int(year), int(month)))
    if not candidates:
        return None
    year, month = max(candidates)
    return f"{year:04d}-{month:02d}"


def _infer_career_stage(raw_text: str, graduation_date: str | None) -> str | None:
    if re.search(r"应届|在校|届毕业生", raw_text):
        return "student" if graduation_date and graduation_date >= date.today().strftime("%Y-%m") else "new_graduate"
    if graduation_date and graduation_date >= date.today().strftime("%Y-%m"):
        return "student"
    if re.search(r"\b(?:[1-9]|10)\+?\s*年工作", raw_text):
        return "experienced"
    return None


def _infer_employment_types(raw_text: str, career_stage: str | None) -> list[str]:
    result: list[str] = []
    intention_lines = "\n".join(line for line in raw_text.splitlines()[:12] if "求职意向" in line)
    if "实习" in intention_lines:
        result.append("internship")
    if re.search(r"应届|全职|校招", intention_lines) or career_stage == "new_graduate":
        result.append("full_time")
    return result


def _clean_target_role(value: str) -> str:
    role = value.split("|", 1)[0].strip()
    role = re.sub(r"\s*[（(](?:20\d{2}\s*届|应届生)[^）)]*[）)]\s*$", "", role)
    return role[:100]


def _build_evidence_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"resume-section-{section.get('order', index)}",
            "type": section.get("type"),
            "title": section.get("title"),
            "content": section.get("content", ""),
        }
        for index, section in enumerate(sections, start=1)
    ]


def _section_items(sections: list[dict[str, Any]], types: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for section in sections:
        if section.get("type") not in types:
            continue
        for index, item in enumerate(section.get("items", []), start=1):
            result.append(
                {
                    "id": f"{section.get('type')}-{section.get('order')}-{index}",
                    "title": item.get("title"),
                    "date": item.get("date"),
                    "content": item.get("content", ""),
                    "source_ref": f"resume-section-{section.get('order')}",
                }
            )
    return result


def _extract_quantified_achievements(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    metric_pattern = re.compile(r"\d+(?:\.\d+)?\s*(?:%|倍|×|卡|B\b|K\b|以上|以下)", re.IGNORECASE)
    for section in sections:
        content = str(section.get("content", ""))
        for sentence in re.split(r"(?<=[。；;])|\n", content):
            sentence = sentence.strip(" -")
            if len(sentence) < 10 or not metric_pattern.search(sentence) or sentence in seen:
                continue
            seen.add(sentence)
            results.append({"claim": sentence[:500], "source_ref": f"resume-section-{section.get('order')}"})
    return results[:30]


def _calculate_experience_months(sections: list[dict[str, Any]]) -> int:
    months: set[int] = set()
    for section in sections:
        if section.get("type") not in {"experience", "internship"}:
            continue
        for item in section.get("items", []):
            matches = re.findall(r"((?:19|20)\d{2})[./-](\d{1,2})", str(item.get("date") or ""))
            if len(matches) < 2:
                continue
            start_y, start_m = map(int, matches[0])
            end_y, end_m = map(int, matches[-1])
            start = start_y * 12 + start_m
            end = end_y * 12 + end_m
            if 0 <= end - start <= 600:
                months.update(range(start, end))
    return len(months)


def _json_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
