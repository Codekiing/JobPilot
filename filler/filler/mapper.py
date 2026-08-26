from __future__ import annotations

from typing import Any

from .models import DraftField


FIELD_ALIASES: dict[str, list[str]] = {
    "full_name": ["姓名", "候选人姓名", "真实姓名", "full name", "candidate name", "name"],
    "email": ["邮箱", "电子邮箱", "邮件地址", "email", "e-mail"],
    "phone": ["手机号", "手机号码", "联系电话", "电话", "mobile", "phone", "telephone"],
    "current_city": ["当前城市", "现居城市", "所在地", "居住地", "current city", "location"],
    "highest_degree": ["最高学历", "学历", "学位", "degree", "education level"],
    "graduation_date": ["毕业时间", "毕业日期", "预计毕业时间", "graduation date", "graduation"],
    "primary_role": ["求职意向", "期望岗位", "目标岗位", "应聘职位", "desired role", "target role"],
    "preferred_locations": ["期望城市", "意向城市", "工作地点", "preferred location", "desired location"],
    "skills": ["技能", "专业技能", "技能标签", "skills", "technical skills"],
    "languages": ["语言能力", "外语能力", "语言", "languages", "language skills"],
    "education_summary": ["教育经历", "教育背景", "教育情况", "education background", "education experience"],
    "experience_summary": ["工作经历", "实习经历", "实践经历", "work experience", "internship experience"],
    "project_summary": ["项目经历", "项目经验", "projects", "project experience"],
    "publication_summary": ["论文", "发表论文", "科研成果", "publications", "research output"],
    "personal_summary": ["个人简介", "自我评价", "个人优势", "补充说明", "summary", "self introduction", "about me"],
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _list_text(values: Any, *, keys: tuple[str, ...] = ("name", "title", "content")) -> str:
    if not isinstance(values, list):
        return ""
    result: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            for key in keys:
                value = _text(item.get(key))
                if value:
                    result.append(value)
                    break
    return "、".join(dict.fromkeys(result))


def _evidence_summary(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    blocks: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        header = " · ".join(filter(None, [_text(item.get("title")), _text(item.get("date"))]))
        content = _text(item.get("content"))
        block = "\n".join(filter(None, [header, content]))
        if block and block not in blocks:
            blocks.append(block)
    return "\n\n".join(blocks)


def build_draft_fields(profile: dict[str, Any]) -> list[DraftField]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    contact = identity.get("contact") if isinstance(identity.get("contact"), dict) else {}
    career = profile.get("career") if isinstance(profile.get("career"), dict) else {}
    target = profile.get("target") if isinstance(profile.get("target"), dict) else {}
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}

    values = {
        "full_name": (_text(identity.get("name")), "identity.name"),
        "email": (_text(contact.get("email")), "identity.contact.email"),
        "phone": (_text(contact.get("phone")), "identity.contact.phone"),
        "current_city": (_text(career.get("current_city")), "career.current_city"),
        "highest_degree": (_text(career.get("highest_degree")), "career.highest_degree"),
        "graduation_date": (_text(career.get("graduation_date")), "career.graduation_date"),
        "primary_role": (_list_text(target.get("primary_roles")), "target.primary_roles"),
        "preferred_locations": (_list_text(target.get("preferred_locations")), "target.preferred_locations"),
        "skills": (_list_text(capabilities.get("skills")), "capabilities.skills"),
        "languages": (_list_text(capabilities.get("languages")), "capabilities.languages"),
        "education_summary": (_evidence_summary(evidence.get("education")), "evidence.education"),
        "experience_summary": (_evidence_summary(evidence.get("experience")), "evidence.experience"),
        "project_summary": (_evidence_summary(evidence.get("projects")), "evidence.projects"),
        "publication_summary": (_evidence_summary(evidence.get("publications")), "evidence.publications"),
    }
    summary_parts = [
        values["primary_role"][0],
        values["skills"][0],
        _list_text(profile.get("preferences", {}).get("culture_keywords") if isinstance(profile.get("preferences"), dict) else []),
    ]
    values["personal_summary"] = ("；".join(part for part in summary_parts if part), "target+capabilities+preferences")

    return [
        DraftField(key=key, value=value, aliases=FIELD_ALIASES[key], source_path=source_path)
        for key, (value, source_path) in values.items()
        if value
    ]
