from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .company_catalog import CompanyCatalog
from .dedupe import deduplicate
from .matching import score_job
from .models import MatchedJob, ProviderResult, utc_now
from .providers.base import Provider
from .query import build_queries


def _diversify_companies(items: list[MatchedJob], limit: int) -> list[MatchedJob]:
    """Keep the score order while preventing one company from filling the page.

    The input is already ranked. We take the best remaining role from every
    company in rounds, so the first screen represents as many employers as the
    candidate pool actually contains. Later rounds still retain every role
    when the requested limit is large enough.
    """
    groups: dict[str, list[MatchedJob]] = {}
    order: list[str] = []
    for index, item in enumerate(items):
        company = item.job.company.strip().casefold()
        key = company or f"__unknown_company_{index}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    diversified: list[MatchedJob] = []
    round_index = 0
    while len(diversified) < limit:
        added = False
        for key in order:
            group = groups[key]
            if round_index < len(group):
                diversified.append(group[round_index])
                added = True
                if len(diversified) >= limit:
                    break
        if not added:
            break
        round_index += 1
    return diversified


@dataclass(slots=True)
class MatchRun:
    profile_id: str
    created_at: str
    queries: list[str]
    jobs: list[MatchedJob]
    providers: list[ProviderResult]
    raw_job_count: int
    deduplicated_job_count: int
    coverage: dict[str, Any]

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
                "official_job_count": sum(job.job.source_kind == "official" for job in self.jobs),
                "platform_job_count": sum(job.job.source_kind == "public_platform" for job in self.jobs),
            },
            "coverage": self.coverage,
            "providers": [provider.summary() for provider in self.providers],
            "jobs": [job.to_dict() for job in self.jobs],
        }


class MatchEngine:
    def __init__(self, providers: list[Provider], *, company_catalog: CompanyCatalog | None = None) -> None:
        self.providers = providers
        self.company_catalog = company_catalog

    def run(
        self,
        profile: dict[str, Any],
        *,
        queries: list[str] | None = None,
        min_score: float = 0,
        limit: int = 100,
        diversify_companies: bool = True,
    ) -> MatchRun:
        resolved_queries = queries or build_queries(profile)
        ordered_providers = sorted(self.providers, key=lambda provider: provider.priority)
        provider_results = [provider.collect(profile, resolved_queries) for provider in ordered_providers]
        for provider, result in zip(ordered_providers, provider_results):
            result.metadata.setdefault("phase", "official_first" if provider.source_kind == "official" else "platform_supplement")
            for job in result.jobs:
                job.source_kind = provider.source_kind
                job.discovered_from = job.discovered_from or result.source
                if self.company_catalog:
                    job.company_tier = self.company_catalog.classify(job.company)
                    if job.source_kind == "official" or self.company_catalog.is_official_application_url(job.company, job.application_url):
                        job.application_source = "official"
                    job.company = self.company_catalog.canonical_name(job.company)
        raw_jobs = [job for result in provider_results for job in result.jobs]
        unique_jobs = deduplicate(raw_jobs)
        matched = [MatchedJob(job=job, match=score_job(profile, job)) for job in unique_jobs]
        matched = [item for item in matched if item.match.total >= min_score]
        matched.sort(
            key=lambda item: (
                item.match.hard_constraints_passed,
                item.match.total,
                item.job.source_kind == "official",
            ),
            reverse=True,
        )
        selected = _diversify_companies(matched, limit) if diversify_companies else matched[:limit]
        coverage = self.company_catalog.coverage(unique_jobs) if self.company_catalog else {}
        official_jobs = [job for job in unique_jobs if job.source_kind == "official"]
        official_companies = {
            self.company_catalog.canonical_name(job.company) if self.company_catalog else job.company
            for job in official_jobs
            if job.company
        }
        official_companies_by_tier = {
            tier: len({job.company for job in official_jobs if job.company_tier == tier})
            for tier in ("major", "mid_size", "unicorn", "growth")
        }
        coverage.update(
            {
                "official_candidates": len(official_jobs),
                "platform_candidates": sum(job.source_kind == "public_platform" for job in unique_jobs),
                "official_companies_with_jobs": len(official_companies),
                "official_companies_with_jobs_by_tier": official_companies_by_tier,
                "platform_small_business_candidates": sum(
                    job.source_kind == "public_platform" and job.company_tier == "small_business"
                    for job in unique_jobs
                ),
            }
        )
        return MatchRun(
            profile_id=str(profile.get("profile_id", "unknown")),
            created_at=utc_now(),
            queries=resolved_queries,
            jobs=selected,
            providers=provider_results,
            raw_job_count=len(raw_jobs),
            deduplicated_job_count=len(unique_jobs),
            coverage=coverage,
        )
