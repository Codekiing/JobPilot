from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ResumeProfile:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    job_intention: str | None = None
    links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeItem:
    order: int
    title: str
    content: str
    date: str | None = None


@dataclass(slots=True)
class ResumeSection:
    order: int
    type: str
    title: str
    content: str
    items: list[ResumeItem] = field(default_factory=list)


@dataclass(slots=True)
class ResumeDocument:
    schema_version: str
    source: dict[str, Any]
    profile: ResumeProfile
    sections: list[ResumeSection]
    raw_text: str
    warnings: list[str] = field(default_factory=list)
    extraction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
