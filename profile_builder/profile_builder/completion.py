from __future__ import annotations

from typing import Any

from .models import UserProfile
from .utils import get_path, is_present


RULES: tuple[dict[str, Any], ...] = (
    {"id": "identity", "path": "identity.name", "weight": 6, "required": True, "label": "姓名"},
    {"id": "phone", "path": "identity.contact.phone", "weight": 8, "required": True, "label": "手机号"},
    {"id": "email", "path": "identity.contact.email", "weight": 8, "required": True, "label": "邮箱"},
    {"id": "gender", "path": "identity.gender", "weight": 3, "required": False, "label": "性别"},
    {"id": "birth_date", "path": "identity.birth_date", "weight": 3, "required": False, "label": "出生日期"},
    {"id": "current_city", "path": "career.current_city", "weight": 5, "required": False, "label": "现居城市"},
    {"id": "highest_degree", "path": "career.highest_degree", "weight": 6, "required": True, "label": "最高学历"},
    {"id": "graduation_date", "path": "career.graduation_date", "weight": 6, "required": False, "label": "毕业日期"},
    {"id": "education", "path": "evidence.education", "weight": 14, "required": True, "label": "教育经历", "min_count": 1},
    {"id": "experience", "path": "evidence.experience", "weight": 12, "required": False, "label": "实习 / 工作经历", "min_count": 1},
    {"id": "projects", "path": "evidence.projects", "weight": 10, "required": False, "label": "项目经历", "min_count": 1},
    {"id": "skills", "path": "capabilities.skills", "weight": 10, "required": True, "label": "技能", "min_count": 3},
    {"id": "languages", "path": "capabilities.languages", "weight": 5, "required": False, "label": "语言能力"},
    {"id": "links", "path": "identity.contact.links", "weight": 4, "required": False, "label": "个人链接"},
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
        missing_recommended = [item for item in missing_recommended if item["field_path"] != "career.graduation_date"]
        missing_required.append({"field_path": "career.graduation_date", "label": "毕业日期"})

    return {
        "score": round(earned / total * 100),
        "match_ready": not missing_required,
        "completed_rules": completed,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
    }
