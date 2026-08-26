from __future__ import annotations

from typing import Any

from .models import UserProfile
from .utils import get_path, is_present


RULES: tuple[dict[str, Any], ...] = (
    {"id": "identity", "path": "identity.name", "weight": 5, "required": True, "label": "姓名"},
    {"id": "career_stage", "path": "career.career_stage", "weight": 6, "required": True, "label": "职业阶段"},
    {"id": "education", "path": "career.highest_degree", "weight": 5, "required": True, "label": "最高学历"},
    {"id": "employment_types", "path": "target.employment_types", "weight": 9, "required": True, "label": "求职类型"},
    {"id": "roles", "path": "target.primary_roles", "weight": 14, "required": True, "label": "目标岗位"},
    {"id": "locations", "path": "target.preferred_locations", "weight": 10, "required": True, "label": "首选城市"},
    {"id": "availability", "path": "target.available_from", "weight": 8, "required": True, "label": "可入职日期"},
    {"id": "work_modes", "path": "target.work_modes", "weight": 5, "required": True, "label": "办公方式"},
    {"id": "job_search_status", "path": "career.job_search_status", "weight": 5, "required": True, "label": "求职状态"},
    {"id": "skills", "path": "capabilities.skills", "weight": 12, "required": True, "label": "技能证据", "min_count": 3},
    {"id": "evidence", "path": "evidence.resume_sections", "weight": 7, "required": True, "label": "经历证据"},
    {"id": "industries", "path": "target.preferred_industries", "weight": 4, "required": False, "label": "意向行业"},
    {"id": "salary", "path": "target.salary.monthly_min_cny", "weight": 4, "required": False, "label": "最低薪资"},
    {"id": "company_preferences", "path": "preferences.company_sizes", "weight": 3, "required": False, "label": "公司偏好"},
    {"id": "constraints", "path": "constraints.deal_breakers", "weight": 3, "required": False, "label": "不可接受条件"},
)


def calculate_completion(profile: UserProfile) -> dict[str, Any]:
    data = profile.to_dict()
    earned = 0
    total = sum(int(rule["weight"]) for rule in RULES)
    missing_required: list[dict[str, str]] = []
    missing_recommended: list[dict[str, str]] = []
    completed: list[str] = []

    for rule in RULES:
        value = get_path(data, str(rule["path"]))
        present = is_present(value)
        if present and rule.get("min_count"):
            present = isinstance(value, list) and len(value) >= int(rule["min_count"])
        if present:
            earned += int(rule["weight"])
            completed.append(str(rule["id"]))
            continue
        missing = {"field_path": str(rule["path"]), "label": str(rule["label"])}
        if rule["required"]:
            missing_required.append(missing)
        else:
            missing_recommended.append(missing)

    # Graduation date is a hard condition only for students/new graduates.
    stage = get_path(data, "career.career_stage")
    if stage in {"student", "new_graduate"} and not is_present(get_path(data, "career.graduation_date")):
        missing_required.append({"field_path": "career.graduation_date", "label": "毕业日期"})

    return {
        "score": round(earned / total * 100),
        "match_ready": not missing_required,
        "completed_rules": completed,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
    }
