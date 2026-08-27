from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Job:
    source: str
    source_job_id: str
    title: str
    company: str = ""
    locations: list[str] = field(default_factory=list)
    employment_type: str = "unknown"
    description: str = ""
    requirements: str = ""
    tags: list[str] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "CNY"
    salary_period: str | None = None
    education: str | None = None
    experience: str | None = None
    industry: str | None = None
    published_at: str | None = None
    deadline: str | None = None
    url: str = ""
    application_url: str = ""
    source_kind: str = "public_platform"
    company_tier: str = "unknown"
    discovered_from: str = ""
    application_source: str = "public_platform"
    collected_at: str = field(default_factory=utc_now)
    source_payload: dict[str, Any] = field(default_factory=dict)

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.title,
                self.company,
                *self.locations,
                self.description,
                self.requirements,
                *self.tags,
                self.education or "",
                self.experience or "",
                self.industry or "",
            ]
        ).lower()

    def to_dict(self, include_payload: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_payload:
            data.pop("source_payload", None)
        return data


@dataclass(slots=True)
class MatchScore:
    total: float
    grade: str
    hard_constraints_passed: bool
    breakdown: dict[str, float]
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatchedJob:
    job: Job
    match: MatchScore

    def to_dict(self) -> dict[str, Any]:
        return {**self.job.to_dict(), "match": self.match.to_dict()}


@dataclass(slots=True)
class ProviderResult:
    source: str
    status: str
    jobs: list[Job] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    discovery_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=utc_now)

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "job_count": len(self.jobs),
            "queries": self.queries,
            "discovery_urls": self.discovery_urls,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "collected_at": self.collected_at,
        }
