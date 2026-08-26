from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Quota:
    limit: int
    confirmed: bool
    source: str
    verification_status: str = "unverified"
    source_url: str = ""
    verified_at: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "confirmed": self.confirmed,
            "source": self.source,
            "verification_status": self.verification_status,
            "source_url": self.source_url,
            "verified_at": self.verified_at,
            "note": self.note,
        }


@dataclass(slots=True)
class JobGroup:
    group_id: str
    company: str
    employment_type: str
    quota: Quota
    jobs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "company": self.company,
            "employment_type": self.employment_type,
            "quota": self.quota.to_dict(),
            "jobs": self.jobs,
        }
