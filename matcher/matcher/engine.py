from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .dedupe import deduplicate
from .matching import score_job
from .models import MatchedJob, ProviderResult, utc_now
from .providers.base import Provider
from .query import build_queries


@dataclass(slots=True)
class MatchRun:
    profile_id: str
    created_at: str
    queries: list[str]
    jobs: list[MatchedJob]
    providers: list[ProviderResult]
    raw_job_count: int
    deduplicated_job_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "component": "matcher",
            "component_version": "0.1.0",
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "queries": self.queries,
            "summary": {
                "raw_job_count": self.raw_job_count,
                "deduplicated_job_count": self.deduplicated_job_count,
                "matched_job_count": len(self.jobs),
                "source_count": len(self.providers),
            },
            "providers": [provider.summary() for provider in self.providers],
            "jobs": [job.to_dict() for job in self.jobs],
        }


class MatchEngine:
    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers

    def run(
        self,
        profile: dict[str, Any],
        *,
        queries: list[str] | None = None,
        min_score: float = 0,
        limit: int = 100,
    ) -> MatchRun:
        resolved_queries = queries or build_queries(profile)
        provider_results = [provider.collect(profile, resolved_queries) for provider in self.providers]
        raw_jobs = [job for result in provider_results for job in result.jobs]
        unique_jobs = deduplicate(raw_jobs)
        matched = [MatchedJob(job=job, match=score_job(profile, job)) for job in unique_jobs]
        matched = [item for item in matched if item.match.total >= min_score]
        matched.sort(key=lambda item: (item.match.hard_constraints_passed, item.match.total), reverse=True)
        return MatchRun(
            profile_id=str(profile.get("profile_id", "unknown")),
            created_at=utc_now(),
            queries=resolved_queries,
            jobs=matched[:limit],
            providers=provider_results,
            raw_job_count=len(raw_jobs),
            deduplicated_job_count=len(unique_jobs),
        )
