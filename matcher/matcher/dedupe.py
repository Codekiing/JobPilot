from __future__ import annotations

import re

from .models import Job


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


def deduplicate(jobs: list[Job]) -> list[Job]:
    result: list[Job] = []
    exact: set[tuple[str, str]] = set()
    semantic: dict[tuple[str, str, str], int] = {}
    for job in jobs:
        exact_key = (job.source, job.source_job_id)
        if exact_key in exact:
            continue
        exact.add(exact_key)
        location = _key(job.locations[0]) if job.locations else ""
        broad_key = (_key(job.company), _key(job.title), location)
        if broad_key in semantic and broad_key[0] and broad_key[1]:
            existing = result[semantic[broad_key]]
            existing_quality = 2 if existing.source_kind == "official" else 1 if existing.application_url else 0
            job_quality = 2 if job.source_kind == "official" else 1 if job.application_url else 0
            if job_quality > existing_quality or (
                job_quality == existing_quality
                and len(job.description) + len(job.requirements) > len(existing.description) + len(existing.requirements)
            ):
                result[semantic[broad_key]] = job
            continue
        semantic[broad_key] = len(result)
        result.append(job)
    return result
