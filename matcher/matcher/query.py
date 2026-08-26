from __future__ import annotations

import re
from typing import Any


DOMAIN_TERMS = (
    "大模型",
    "后训练",
    "强化学习",
    "多模态",
    "自然语言处理",
    "机器学习",
    "深度学习",
    "推荐算法",
    "搜索算法",
    "计算机视觉",
    "算法",
    "Agent",
    "RLHF",
    "RAG",
    "NLP",
    "LLM",
)


def clean_role(role: str) -> str:
    role = re.sub(r"[（(].*?[）)]", "", role).strip()
    role = re.sub(r"\s*/\s*", " ", role)
    return re.sub(r"\s+", " ", role)


def meaningful_terms(text: str) -> list[str]:
    lower = text.lower()
    result: list[str] = []
    for term in DOMAIN_TERMS:
        if term.lower() in lower and term.lower() not in {x.lower() for x in result}:
            result.append(term)
    for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{1,20}", text):
        if term.lower() not in {x.lower() for x in result}:
            result.append(term)
    return result


def build_queries(profile: dict[str, Any], limit: int = 3) -> list[str]:
    target = profile.get("target", {})
    roles = [clean_role(str(role)) for role in target.get("primary_roles", []) + target.get("secondary_roles", [])]
    roles = [role for role in roles if role]
    queries: list[str] = []
    for role in roles:
        if role not in queries:
            queries.append(role)
    skill_names = [
        str(skill.get("name", ""))
        for skill in profile.get("capabilities", {}).get("skills", [])
        if skill.get("proficiency") in {"advanced", "intermediate"}
    ]
    if roles:
        role_terms = meaningful_terms(" ".join(roles))
        extras = [skill for skill in skill_names if skill.lower() not in " ".join(roles).lower()]
        if role_terms and extras:
            queries.append(f"{role_terms[0]} {extras[0]}")
    elif skill_names:
        queries.append(" ".join(skill_names[:2]))
    if not queries:
        queries.append("软件工程师")
    unique: list[str] = []
    for query in queries:
        if query and query not in unique:
            unique.append(query)
    return unique[: max(1, limit)]
