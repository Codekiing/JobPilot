from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

from ..company_catalog import TIER_ORDER, CompanyCatalog, CompanyTarget
from ..http import request_json, request_text
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
    priority = 10
    source_kind = "official"

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
                        source_kind="official",
                        discovered_from=page_url,
                        application_source="official",
                    )
                )
        jobs.extend(self._parse_initial_data(page, page_url))
        return jobs

    def _parse_initial_data(self, page: str, page_url: str) -> list[Job]:
        """Parse SSR job records used by several official career sites.

        This intentionally requires a conservative field signature so random
        application state is never turned into a job record.
        """
        match = re.search(r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\})\s*;\s*window\.", page, re.S)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            return []
        jobs: list[Job] = []
        for item in _walk(data):
            if not item.get("name") or not item.get("postId"):
                continue
            if not any(key in item for key in ("workContent", "serviceCondition", "workPlace", "postType")):
                continue
            employment = "internship" if "实习" in str(item.get("projectType") or "") else "campus"
            post_id = str(item["postId"])
            recruit_type = "INTERN" if employment == "internship" else "GRADUATE"
            detail_url = urljoin(page_url, f"/jobs/detail/{recruit_type}/{post_id}")
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=post_id,
                    title=_strip_html(item.get("name")),
                    company=_strip_html(item.get("orgName")),
                    locations=[_strip_html(item.get("workPlace"))] if item.get("workPlace") else [],
                    employment_type=employment,
                    description=_strip_html(item.get("workContent")),
                    requirements=_strip_html(item.get("serviceCondition")),
                    tags=[_strip_html(item.get("postType"))] if item.get("postType") else [],
                    education=_strip_html(item.get("education")) or None,
                    published_at=str(item.get("updateDate") or item.get("publishDate") or "") or None,
                    url=detail_url,
                    application_url=detail_url,
                    source_kind="official",
                    discovered_from=page_url,
                    application_source="official",
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


def _query_terms(queries: list[str]) -> list[str]:
    terms: list[str] = []
    role_tokens = ("大模型", "机器学习", "算法", "数据", "前端", "后端", "开发", "测试", "产品", "运营", "设计", "安全", "嵌入式", "硬件", "研究")
    for query in queries:
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9+.#-]+", query))
        terms.extend(token for token in role_tokens if token in query)
    return list(dict.fromkeys(term.lower() for term in terms if term.strip()))


class CompanyCatalogProvider(CompanyCareersProvider):
    """Search a maintained company list before any recruitment platform.

    The provider intentionally records every attempted official career URL. A
    page that cannot be parsed is reported as uncovered instead of being
    silently interpreted as "no matching jobs".
    """

    name = "official_careers"

    def __init__(
        self,
        catalog: CompanyCatalog,
        *,
        tiers: list[str] | None = None,
        workers: int = 10,
        **kwargs: Any,
    ) -> None:
        super().__init__([], **kwargs)
        self.catalog = catalog
        self.tiers = tiers
        self.workers = max(1, min(20, workers))

    def _parse_tencent_payload(self, payload: dict[str, Any], page_url: str) -> list[Job]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        records = data.get("positionList") if isinstance(data.get("positionList"), list) else []
        jobs: list[Job] = []
        for item in records:
            if not isinstance(item, dict) or not item.get("positionTitle") or not item.get("postId"):
                continue
            post_id = str(item["postId"])
            detail_url = f"https://join.qq.com/post_detail.html?postid={post_id}"
            locations = [part for part in re.split(r"[、,，\s]+", _strip_html(item.get("workCities"))) if part]
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=post_id,
                    title=_strip_html(item.get("positionTitle")),
                    company="腾讯",
                    locations=locations,
                    employment_type="campus",
                    description=_strip_html(item.get("projectName")),
                    tags=[_strip_html(item.get("positionFamily"))] if item.get("positionFamily") else [],
                    url=detail_url,
                    application_url=detail_url,
                    source_kind="official",
                    discovered_from=page_url,
                    application_source="official",
                    source_payload=item,
                )
            )
        return jobs

    def _parse_kuaishou_payload(self, payload: dict[str, Any], page_url: str) -> list[Job]:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        records = result.get("list") if isinstance(result.get("list"), list) else []
        jobs: list[Job] = []
        for item in records:
            if not isinstance(item, dict) or not item.get("name") or not item.get("id"):
                continue
            position_id = str(item["id"])
            detail_url = f"https://campus.kuaishou.cn/recruit/campus/e#/campus/job-info/{position_id}"
            locations = [
                _strip_html(location.get("name"))
                for location in item.get("workLocationDicts", [])
                if isinstance(location, dict) and location.get("name")
            ]
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=position_id,
                    title=_strip_html(item.get("name")),
                    company="快手",
                    locations=locations,
                    employment_type="internship" if item.get("positionNatureCode") == "intern" else "campus",
                    description=_strip_html(item.get("description")),
                    requirements=_strip_html(item.get("positionDemand")),
                    published_at=str(item.get("releaseTime") or "") or None,
                    url=detail_url,
                    application_url=detail_url,
                    source_kind="official",
                    discovered_from=page_url,
                    application_source="official",
                    source_payload=item,
                )
            )
        return jobs

    def _collect_dynamic_target(self, target: CompanyTarget, url: str) -> list[Job] | None:
        if target.name == "腾讯":
            payload = request_json(
                "https://join.qq.com/api/v1/position/searchPosition",
                timeout=self.timeout,
                method="POST",
                headers={"Referer": url, "Origin": "https://join.qq.com"},
                json_body={
                    "projectIdList": [],
                    "projectMappingIdList": [],
                    "keyword": "",
                    "bgList": [],
                    "workCountryType": 0,
                    "workCityList": [],
                    "recruitCityList": [],
                    "positionFidList": [],
                    "pageIndex": 1,
                    "pageSize": 1000,
                },
            )
            return self._parse_tencent_payload(payload, url)
        if target.name == "快手":
            payload = request_json(
                "https://campus.kuaishou.cn/recruit/campus/e/api/v1/open/positions/simple",
                timeout=self.timeout,
                method="POST",
                headers={"Referer": url, "Origin": "https://campus.kuaishou.cn"},
                json_body={"pageNum": 1, "pageSize": 1000, "name": ""},
            )
            return self._parse_kuaishou_payload(payload, url)
        return None

    def _collect_target(self, target: CompanyTarget, url: str, terms: list[str]) -> tuple[list[Job], str | None]:
        try:
            dynamic_jobs = self._collect_dynamic_target(target, url)
            jobs = dynamic_jobs if dynamic_jobs is not None else self._parse_page(request_text(url, timeout=self.timeout), url)
        except Exception as exc:
            return [], f"{target.name}: {type(exc).__name__}: {exc}"
        selected: list[Job] = []
        for job in jobs:
            searchable = job.searchable_text()
            if terms and not any(term in searchable for term in terms):
                continue
            job.company = job.company or target.name
            job.company_tier = target.tier
            job.source = self.name
            job.source_kind = "official"
            job.application_source = "official"
            job.discovered_from = url
            selected.append(job)
        return selected, None

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        targets = self.catalog.selected(self.tiers)
        attempts = [(target, url) for target in targets for url in target.career_urls]
        result = ProviderResult(
            source=self.name,
            status="success",
            queries=queries,
            discovery_urls=[url for _, url in attempts],
            metadata={
                "phase": "official_first",
                "planned_companies": len(targets),
                "attempted_urls": len(attempts),
                "tiers": self.tiers or [],
            },
        )
        terms = _query_terms(queries)
        reachable_companies: set[str] = set()
        companies_with_jobs: set[str] = set()
        coverage_entries: dict[str, dict[str, Any]] = {
            target.name: {
                "name": target.name,
                "tier": target.tier,
                "career_url": target.career_urls[0] if target.career_urls else "",
                "status": "unreachable",
                "matched_job_count": 0,
            }
            for target in targets
        }
        parse_failures = 0
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._collect_target, target, url, terms): (target, url)
                for target, url in attempts
            }
            for future in as_completed(futures):
                target, url = futures[future]
                jobs, warning = future.result()
                if warning:
                    parse_failures += 1
                    if len(result.warnings) < 12:
                        result.warnings.append(warning)
                    continue
                reachable_companies.add(target.name)
                entry = coverage_entries[target.name]
                entry["career_url"] = url
                if entry["status"] == "unreachable":
                    entry["status"] = "reachable_no_match"
                if jobs:
                    companies_with_jobs.add(target.name)
                    result.jobs.extend(jobs)
                    entry["status"] = "matched"
                    entry["matched_job_count"] = int(entry["matched_job_count"]) + len(jobs)
        result.jobs.sort(
            key=lambda job: (
                TIER_ORDER.index(job.company_tier) if job.company_tier in TIER_ORDER else len(TIER_ORDER),
                job.company,
                job.title,
            )
        )
        if len(result.jobs) > self.max_jobs:
            result.jobs = result.jobs[: self.max_jobs]
        result.metadata.update(
            {
                "companies_with_jobs": len(companies_with_jobs),
                "reachable_companies": len(reachable_companies),
                "reachable_companies_by_tier": {
                    tier: sum(target.name in reachable_companies for target in targets if target.tier == tier)
                    for tier in TIER_ORDER
                    if any(target.tier == tier for target in targets)
                },
                "companies_with_jobs_by_tier": {
                    tier: sum(target.name in companies_with_jobs for target in targets if target.tier == tier)
                    for tier in TIER_ORDER
                    if any(target.tier == tier for target in targets)
                },
                "parse_failures": parse_failures,
                "unreachable_companies": len(targets) - len(reachable_companies),
                "uncovered_companies": len(targets) - len(companies_with_jobs),
                "coverage_entries": list(coverage_entries.values()),
            }
        )
        if result.jobs and (parse_failures or len(companies_with_jobs) < len(targets)):
            result.status = "partial"
        elif not result.jobs:
            result.status = "empty" if not parse_failures else "partial"
            result.warnings.append("已搜索官网清单，但未从公开页面解析到与画像相关的结构化岗位；这些公司不会被误报为无岗位")
        return result
