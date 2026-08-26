from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urljoin

from ..http import request_text
from ..models import Job, ProviderResult
from .base import Provider


def _strip_html(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


class CompanyCareersProvider(Provider):
    name = "company_careers"

    def __init__(self, urls: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.urls = urls

    def _parse_page(self, page: str, page_url: str) -> list[Job]:
        jobs: list[Job] = []
        scripts = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.I | re.S
        )
        for script in scripts:
            try:
                data = json.loads(html.unescape(script.strip()))
            except (json.JSONDecodeError, ValueError):
                continue
            for item in _walk(data):
                item_type = item.get("@type")
                if not (item_type == "JobPosting" or isinstance(item_type, list) and "JobPosting" in item_type):
                    continue
                organization = item.get("hiringOrganization") or {}
                locations_raw = item.get("jobLocation") or []
                if isinstance(locations_raw, dict):
                    locations_raw = [locations_raw]
                locations: list[str] = []
                for location in locations_raw:
                    address = location.get("address", {}) if isinstance(location, dict) else {}
                    if isinstance(address, str):
                        locations.append(address)
                    elif isinstance(address, dict):
                        value = "".join(str(address.get(k) or "") for k in ("addressRegion", "addressLocality"))
                        if value:
                            locations.append(value)
                identifier = item.get("identifier") or {}
                source_id = identifier.get("value") if isinstance(identifier, dict) else identifier
                job_url = urljoin(page_url, str(item.get("url") or page_url))
                jobs.append(
                    Job(
                        source=self.name,
                        source_job_id=str(source_id or job_url),
                        title=str(item.get("title") or ""),
                        company=str(organization.get("name") if isinstance(organization, dict) else organization or ""),
                        locations=locations,
                        employment_type=str(item.get("employmentType") or "unknown").lower(),
                        description=_strip_html(item.get("description")),
                        education=_strip_html(item.get("educationRequirements")) or None,
                        experience=_strip_html(item.get("experienceRequirements")) or None,
                        published_at=str(item.get("datePosted") or "") or None,
                        deadline=str(item.get("validThrough") or "") or None,
                        url=job_url,
                        application_url=job_url,
                    )
                )
        return jobs

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        if not self.urls:
            return ProviderResult(source=self.name, status="skipped", queries=queries, warnings=["未提供 --career-url"])
        result = ProviderResult(source=self.name, status="success", queries=queries, discovery_urls=self.urls.copy())
        for url in self.urls:
            try:
                result.jobs.extend(self._parse_page(request_text(url, timeout=self.timeout), url))
            except Exception as exc:
                result.status = "partial" if result.jobs else "failed"
                result.warnings.append(f"{url}: {type(exc).__name__}: {exc}")
        if len(result.jobs) > self.max_jobs:
            result.jobs = result.jobs[: self.max_jobs]
        if not result.jobs and result.status == "success":
            result.status = "empty"
            result.warnings.append("页面中未发现 JobPosting JSON-LD；可使用 --import-jobs 导入该官网导出结果")
        return result
