from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ResumeItem, ResumeProfile, ResumeSection


SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("个人总结", "职业概述", "个人简介", "summary", "profile", "objective"),
    "education": ("教育背景", "教育经历", "教育", "education", "academic background"),
    "experience": ("工作经历", "工作经验", "任职经历", "experience", "work experience", "employment"),
    "internship": ("实习经历", "实习经验", "internship", "internships"),
    "project": ("项目经历", "项目经验", "项目", "projects", "project experience"),
    "research": ("科研经历", "研究经历", "research", "research experience"),
    "open_source": ("开源贡献", "开源经历", "open source", "open-source contributions"),
    "publications": ("论文经历", "论文发表", "论文", "学术成果", "publications", "papers"),
    "skills": ("核心技能", "专业技能", "技能", "技能特长", "skills", "technical skills"),
    "awards": ("荣誉奖项", "奖项荣誉", "获奖经历", "awards", "honors", "honours"),
    "certifications": ("证书", "资格证书", "certifications", "certificates"),
    "languages": ("语言能力", "语言", "languages"),
    "activities": ("校园经历", "社团经历", "志愿经历", "activities", "leadership"),
    "self_evaluation": ("自我评价", "个人评价", "self evaluation"),
}

CANONICAL_TITLES = {
    "basic_info": "基本信息",
    "summary": "个人总结",
    "education": "教育背景",
    "experience": "工作经历",
    "internship": "实习经历",
    "project": "项目经历",
    "research": "科研经历",
    "open_source": "开源贡献",
    "publications": "论文经历",
    "skills": "核心技能",
    "awards": "荣誉奖项",
    "certifications": "资格证书",
    "languages": "语言能力",
    "activities": "校园经历",
    "self_evaluation": "自我评价",
    "other": "其他",
}

_ALIAS_LOOKUP = {
    alias.casefold(): section_type
    for section_type, aliases in SECTION_ALIASES.items()
    for alias in aliases
}
_DATE_RANGE = re.compile(
    r"(?P<date>(?:19|20)\d{2}(?:[./年-]\d{1,2}月?)?\s*(?:-|–|—|~|至|到)\s*(?:(?:19|20)\d{2}(?:[./年-]\d{1,2}月?)?|至今|现在|present|current))",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)|(?<!\d)\+?\d[\d ()-]{7,}\d")
_URL = re.compile(r"(?:https?://|www\.)[^\s|，；]+", re.IGNORECASE)


@dataclass(slots=True)
class Heading:
    section_type: str
    title: str
    markdown: bool = False


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = text.replace("▪", "- ").replace("●", "- ").replace("•", "- ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    compact: list[str] = []
    for line in lines:
        if not line:
            if compact and compact[-1] != "":
                compact.append("")
            continue
        compact.append(line)
    return "\n".join(compact).strip()


def identify_heading(line: str) -> Heading | None:
    markdown_match = re.match(r"^#{1,4}\s+(.+?)\s*#*$", line)
    candidate = markdown_match.group(1).strip() if markdown_match else line.strip()
    normalized = re.sub(r"[：:]$", "", candidate).strip().casefold()
    if normalized in _ALIAS_LOOKUP:
        section_type = _ALIAS_LOOKUP[normalized]
        return Heading(section_type, candidate, bool(markdown_match))
    if markdown_match and len(candidate) <= 60:
        return Heading("other", candidate, True)
    return None


def extract_profile(text: str) -> ResumeProfile:
    lines = [line for line in text.splitlines() if line.strip()]
    email_match = _EMAIL.search(text)
    phone_match = _PHONE.search(text)
    links = list(dict.fromkeys(match.group(0).rstrip(".,)") for match in _URL.finditer(text)))
    name = _guess_name(lines)
    job_intention = None
    location = None
    for line in lines[:20]:
        match = re.search(r"(?:求职意向|目标岗位|应聘职位|objective)\s*[：:]\s*(.+)", line, re.IGNORECASE)
        if match:
            job_intention = match.group(1).strip()
        match = re.search(r"(?:所在地|现居地|城市|location)\s*[：:]\s*([^|｜,，]+)", line, re.IGNORECASE)
        if match:
            location = match.group(1).strip()
    return ResumeProfile(
        name=name,
        email=email_match.group(0) if email_match else None,
        phone=re.sub(r"\s+", " ", phone_match.group(0)).strip() if phone_match else None,
        location=location,
        job_intention=job_intention,
        links=links,
    )


def _guess_name(lines: list[str]) -> str | None:
    for raw_line in lines[:8]:
        line = re.sub(r"^#+\s*", "", raw_line).strip()
        heading = identify_heading(raw_line)
        if (heading and heading.section_type != "other") or _EMAIL.search(line) or _PHONE.search(line):
            continue
        if re.search(r"求职意向|电话|邮箱|email|phone|resume|简历", line, re.IGNORECASE):
            continue
        if re.fullmatch(r"[\u4e00-\u9fff·]{2,8}", line):
            return line
        if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,39}", line) and len(line.split()) <= 5:
            return line
    return None


def split_sections(text: str) -> list[ResumeSection]:
    normalized_text = normalize_text(text)
    lines = normalized_text.splitlines()
    raw_sections: list[tuple[str, str, list[str]]] = []
    current_type = "basic_info"
    current_title = CANONICAL_TITLES[current_type]
    current_lines: list[str] = []
    seen_content = False

    for line in lines:
        heading = identify_heading(line)
        # Treat a leading custom Markdown H1 as the resume title/name, not a section.
        if heading and heading.section_type == "other" and not seen_content and not current_lines:
            current_lines.append(re.sub(r"^#+\s*", "", line))
            seen_content = True
            continue
        if heading:
            if current_lines or current_type != "basic_info":
                raw_sections.append((current_type, current_title, _trim_blank_lines(current_lines)))
            current_type = heading.section_type
            current_title = heading.title
            current_lines = []
            seen_content = True
            continue
        current_lines.append(line)
        if line:
            seen_content = True
    if current_lines or not raw_sections:
        raw_sections.append((current_type, current_title, _trim_blank_lines(current_lines)))

    sections: list[ResumeSection] = []
    for section_type, title, content_lines in raw_sections:
        content = "\n".join(content_lines).strip()
        if not content and section_type == "basic_info":
            continue
        order = len(sections) + 1
        sections.append(
            ResumeSection(
                order=order,
                type=section_type,
                title=title,
                content=content,
                items=_split_items(section_type, content),
            )
        )
    return sections


def _trim_blank_lines(lines: list[str]) -> list[str]:
    result = list(lines)
    while result and not result[0]:
        result.pop(0)
    while result and not result[-1]:
        result.pop()
    return result


def _split_items(section_type: str, content: str) -> list[ResumeItem]:
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        return []

    if section_type in {"skills", "publications", "awards", "certifications", "languages"}:
        return [
            ResumeItem(order=i, title=_item_title(line), content=line)
            for i, line in enumerate(lines, start=1)
        ]

    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _DATE_RANGE.search(line) and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)

    # Sections without detectable entries are still represented by one item.
    if len(groups) == 1 and not _DATE_RANGE.search(groups[0][0]):
        return [ResumeItem(order=1, title=_item_title(groups[0][0]), content="\n".join(groups[0]))]

    items: list[ResumeItem] = []
    for index, group in enumerate(groups, start=1):
        joined = "\n".join(group)
        date_match = _DATE_RANGE.search(group[0])
        heading = _DATE_RANGE.sub("", group[0]).strip(" |—-：:") if date_match else group[0]
        items.append(
            ResumeItem(
                order=index,
                title=_item_title(heading or group[0]),
                content=joined,
                date=date_match.group("date") if date_match else None,
            )
        )
    return items


def _item_title(line: str) -> str:
    line = re.sub(r"^[-*+]\s*", "", line).strip()
    if "：" in line:
        line = line.split("：", 1)[0]
    elif ":" in line and not re.match(r"https?://", line, re.IGNORECASE):
        line = line.split(":", 1)[0]
    return line[:120]
