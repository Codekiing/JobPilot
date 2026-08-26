from __future__ import annotations

import hashlib
import html
import re
from typing import Any
from urllib.parse import quote_plus

from ..http import request_text
from ..models import Job, ProviderResult
from ..profile import employment_types
from .base import Provider


class ShixisengProvider(Provider):
    name = "shixiseng"

    @staticmethod
    def _clean(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    def _parse(self, page: str) -> list[Job]:
        starts = [match.start() for match in re.finditer(r'<div\s+data-intern-id="', page)]
        jobs: list[Job] = []
        for index, start in enumerate(starts):
            block = page[start : starts[index + 1] if index + 1 < len(starts) else start + 10000]
            job_id_match = re.search(r'data-intern-id="([^"]+)"', block)
            title_match = re.search(
                r'<a\s+href="([^"]*/intern/[^"]+)"\s+title="([^"]+)"[^>]*>(.*?)</a>', block, re.S
            )
            if not job_id_match or not title_match:
                continue
            company_block = ""
            marker = block.find("intern-detail__company")
            if marker >= 0:
                company_block = block[marker : marker + 2500]
            company_match = re.search(r'<a\s+title="([^"]+)"', company_block)
            city_match = re.search(r'class="city[^>]*>(.*?)</span>', block, re.S)
            degree_match = re.search(r'"degree":"?([^",}]+)', block)
            labels = [self._clean(value) for value in re.findall(r'class="intern-label"[^>]*>(.*?)</span>', block, re.S)]
            title = self._clean(title_match.group(2) or title_match.group(3))
            job_url = html.unescape(title_match.group(1))
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=job_id_match.group(1),
                    title=title,
                    company=self._clean(company_match.group(1)) if company_match else "",
                    locations=[self._clean(city_match.group(1))] if city_match else [],
                    employment_type="internship",
                    tags=[label for label in labels if label],
                    education=self._clean(degree_match.group(1)) if degree_match else None,
                    url=job_url,
                    application_url=job_url,
                )
            )
        return jobs

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        if "internship" not in employment_types(profile):
            return ProviderResult(
                source=self.name,
                status="skipped",
                queries=queries,
                discovery_urls=["https://www.shixiseng.com/interns"],
                warnings=["画像未选择实习岗位，因此未采集实习僧"],
            )
        result = ProviderResult(source=self.name, status="success", queries=queries)
        seen: set[str] = set()
        for query in queries:
            url = f"https://www.shixiseng.com/interns?keyword={quote_plus(query)}"
            result.discovery_urls.append(url)
            try:
                jobs = self._parse(request_text(url, timeout=self.timeout))
                for job in jobs:
                    if job.source_job_id not in seen:
                        seen.add(job.source_job_id)
                        result.jobs.append(job)
                        if len(result.jobs) >= self.max_jobs:
                            return result
            except Exception as exc:  # network and page changes are reported per provider
                result.status = "partial" if result.jobs else "failed"
                result.warnings.append(f"采集失败：{type(exc).__name__}: {exc}")
        if not result.jobs and result.status == "success":
            result.status = "empty"
        return result
