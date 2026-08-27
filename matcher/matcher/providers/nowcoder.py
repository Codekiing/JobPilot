from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..http import request_json
from ..models import Job, ProviderResult
from ..profile import employment_types
from ..company_catalog import CompanyCatalog
from .base import Provider


EDUCATION = {
    0: "不限",
    1000: "不限",
    3000: "大专",
    5000: "本科",
    6000: "硕士",
    7000: "博士",
}


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _salary_value(value: Any, recruit_type: int) -> float | int | None:
    if not isinstance(value, (int, float)) or value <= 0 or value >= 999999:
        return None
    return value if recruit_type == 2 else value * 1000


def _experience(data: dict[str, Any], recruit_type: int) -> str | None:
    explicit = (data.get("jobExpInfo") or {}).get("expTag")
    if explicit:
        return str(explicit)
    if recruit_type == 1:
        return "应届生"
    if recruit_type == 2:
        return "实习"
    return {
        0: "经验不限",
        1: "1年以内",
        2: "1-3年",
        3: "3-5年",
        4: "5-10年",
        5: "10年以上",
    }.get(data.get("workYearType"))


class NowcoderProvider(Provider):
    name = "nowcoder"
    endpoint = "https://mnowpick.nowcoder.com/u/job/square-search"

    def _recruit_type(self, profile: dict[str, Any]) -> int:
        types = employment_types(profile)
        if "internship" in types and "full_time" not in types:
            return 2
        if profile.get("career", {}).get("career_stage") == "student":
            return 1
        return 3

    def _parse(self, raw: dict[str, Any], recruit_type: int) -> Job | None:
        data = raw.get("data", raw)
        if not isinstance(data, dict) or not data.get("jobName"):
            return None
        ext: dict[str, Any] = {}
        if isinstance(data.get("ext"), str):
            try:
                parsed = json.loads(data["ext"])
                if isinstance(parsed, dict):
                    ext = parsed
            except json.JSONDecodeError:
                pass
        company = data.get("recommendInternCompany") or {}
        company_name = company.get("companyShortName") or company.get("companyName") or ""
        if not company_name:
            identities = (data.get("user") or {}).get("identity") or []
            if identities:
                company_name = identities[0].get("companyName", "")
        job_id = str(data.get("id", ""))
        salary_period = "day" if recruit_type == 2 else "month"
        return Job(
            source=self.name,
            source_job_id=job_id,
            title=str(data.get("jobName", "")),
            company=str(company_name),
            locations=[str(x) for x in (data.get("jobCityList") or [data.get("jobCity")]) if x],
            employment_type={1: "campus", 2: "internship", 3: "full_time"}.get(recruit_type, "unknown"),
            description=str(ext.get("infos", "")),
            requirements=str(ext.get("requirements", "")),
            tags=[x.strip() for x in str(data.get("jobKeys", "")).split(",") if x.strip()],
            salary_min=_salary_value(data.get("salaryMin"), recruit_type),
            salary_max=_salary_value(data.get("salaryMax"), recruit_type),
            salary_period=salary_period,
            education=EDUCATION.get(data.get("eduLevel"), str(data.get("eduLevel") or "")) or None,
            experience=_experience(data, recruit_type),
            industry=(company.get("industryTagNameList") or [None])[0],
            published_at=_timestamp(data.get("refreshTime") or data.get("createTime")),
            url=f"https://www.nowcoder.com/jobs/detail/{job_id}",
            application_url=str(data.get("redirectExternalUrl") or f"https://www.nowcoder.com/jobs/detail/{job_id}"),
            source_payload={"recruit_type": recruit_type},
        )

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        recruit_type = self._recruit_type(profile)
        center = {1: "school/jobs", 2: "intern/center", 3: "fulltime/center"}[recruit_type]
        result = ProviderResult(
            source=self.name,
            status="success",
            queries=queries,
            discovery_urls=[f"https://mnowpick.nowcoder.com/jobs/{center}"],
        )
        seen: set[str] = set()
        for query in queries:
            try:
                response = request_json(
                    self.endpoint,
                    timeout=self.timeout,
                    method="POST",
                    form={
                        "page": 1,
                        "pageSize": min(50, self.max_jobs),
                        "recruitType": recruit_type,
                        "query": query,
                        "random": "false",
                        "recommend": "false",
                        "requestFrom": 1,
                    },
                    headers={"Referer": f"https://mnowpick.nowcoder.com/jobs/{center}"},
                )
                if response.get("code") != 0:
                    raise RuntimeError(response.get("msg") or f"响应码 {response.get('code')}")
                for raw in (response.get("data") or {}).get("datas", []):
                    job = self._parse(raw, recruit_type)
                    if job and job.source_job_id not in seen:
                        seen.add(job.source_job_id)
                        result.jobs.append(job)
                        if len(result.jobs) >= self.max_jobs:
                            return result
            except Exception as exc:
                result.status = "partial" if result.jobs else "failed"
                result.warnings.append(f"采集失败：{type(exc).__name__}: {exc}")
        if not result.jobs and result.status == "success":
            result.status = "empty"
        return result


class NowcoderMajorCompanyProvider(NowcoderProvider):
    """Query every major company by name when its official site is opaque.

    Results remain labelled as Nowcoder discoveries. This is a coverage
    fallback, not an attempt to present platform data as official data.
    """

    name = "nowcoder_company_search"
    priority = 35

    def __init__(self, catalog: CompanyCatalog, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.catalog = catalog

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        recruit_type = self._recruit_type(profile)
        center = {1: "school/jobs", 2: "intern/center", 3: "fulltime/center"}[recruit_type]
        targets = self.catalog.selected(["major"])
        result = ProviderResult(
            source=self.name,
            status="success",
            queries=queries,
            discovery_urls=[f"https://mnowpick.nowcoder.com/jobs/{center}"],
            metadata={"phase": "major_company_fallback", "planned_companies": len(targets)},
        )
        seen: set[str] = set()
        company_counts: dict[str, int] = {}
        page_size = min(50, max(10, self.max_jobs))
        for target in targets:
            try:
                response = request_json(
                    self.endpoint,
                    timeout=self.timeout,
                    method="POST",
                    form={
                        "page": 1,
                        "pageSize": page_size,
                        "recruitType": recruit_type,
                        "query": target.name,
                        "random": "false",
                        "recommend": "false",
                        "requestFrom": 1,
                    },
                    headers={"Referer": f"https://mnowpick.nowcoder.com/jobs/{center}"},
                )
                if response.get("code") != 0:
                    raise RuntimeError(response.get("msg") or f"响应码 {response.get('code')}")
                count = 0
                for raw in (response.get("data") or {}).get("datas", []):
                    job = self._parse(raw, recruit_type)
                    if not job or job.source_job_id in seen:
                        continue
                    identified = self.catalog.identify(job.company)
                    if not identified or identified.name != target.name:
                        continue
                    seen.add(job.source_job_id)
                    result.jobs.append(job)
                    count += 1
                    if len(result.jobs) >= self.max_jobs:
                        break
                company_counts[target.name] = count
            except Exception as exc:
                company_counts[target.name] = 0
                result.warnings.append(f"{target.name}: {type(exc).__name__}: {exc}")
            if len(result.jobs) >= self.max_jobs:
                break
        result.metadata["companies_with_jobs"] = sum(count > 0 for count in company_counts.values())
        result.metadata["company_job_counts"] = company_counts
        if result.warnings:
            result.status = "partial" if result.jobs else "failed"
        elif not result.jobs:
            result.status = "empty"
        return result
