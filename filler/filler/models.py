from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DraftField:
    key: str
    value: str
    aliases: list[str]
    source_path: str
    sensitive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ApplicationDraft:
    draft_id: str
    job_key: str
    company: str
    title: str
    application_url: str
    original_application_url: str
    official_url_source: str
    source_url: str
    adapter: str
    fields: list[DraftField]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "job_key": self.job_key,
            "company": self.company,
            "title": self.title,
            "application_url": self.application_url,
            "original_application_url": self.original_application_url,
            "official_url_source": self.official_url_source,
            "source_url": self.source_url,
            "adapter": self.adapter,
            "fields": [item.to_dict() for item in self.fields],
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class FillPlan:
    plan_id: str
    profile_id: str
    created_at: str
    source_profile_json: str
    source_selected_jobs_json: str
    applications: list[ApplicationDraft]
    missing_required_fields: list[str]
    safety: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "component": "filler",
            "component_version": "0.1.0",
            "plan_id": self.plan_id,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "source_profile_json": self.source_profile_json,
            "source_selected_jobs_json": self.source_selected_jobs_json,
            "summary": {
                "application_count": len(self.applications),
                "missing_required_field_count": len(self.missing_required_fields),
            },
            "missing_required_fields": self.missing_required_fields,
            "safety": self.safety,
            "applications": [item.to_dict() for item in self.applications],
        }
