from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus, urlencode

from ..http import request_json
from ..models import Job, ProviderResult
from .base import Provider


def _salary(value: str) -> tuple[float | None, float | None, str | None]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*K", value, re.I)
    if not match:
        return None, None, None
    return float(match.group(1)) * 1000, float(match.group(2)) * 1000, "month"


class BossProvider(Provider):
    name = "boss"
    endpoint = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        result = ProviderResult(source=self.name, status="success", queries=queries)
        seen: set[str] = set()
        for query in queries:
            params = {"scene": 1, "query": query, "city": "100010000", "page": 1, "pageSize": self.max_jobs}
            api_url = f"{self.endpoint}?{urlencode(params)}"
            search_url = f"https://www.zhipin.com/web/geek/job?query={quote_plus(query)}&city=100010000"
            result.discovery_urls.append(search_url)
            try:
                response = request_json(
                    api_url,
                    timeout=self.timeout,
                    headers={"Referer": search_url},
                )
                if response.get("code") != 0:
                    result.status = "needs_browser"
                    result.warnings.append(
                        "BOSS 返回环境校验，未尝试绕过；请在浏览器打开 discovery_urls，或将导出结果通过 --import-jobs 导入"
                    )
                    break
                for raw in (response.get("zpData") or {}).get("jobList", []):
                    job_id = str(raw.get("encryptJobId") or raw.get("jobId") or "")
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    salary_min, salary_max, salary_period = _salary(str(raw.get("salaryDesc") or ""))
                    detail_url = f"https://www.zhipin.com/job_detail/{job_id}.html"
                    result.jobs.append(
                        Job(
                            source=self.name,
                            source_job_id=job_id,
                            title=str(raw.get("jobName") or ""),
                            company=str(raw.get("brandName") or ""),
                            locations=[str(raw.get("cityName") or "")],
                            employment_type="full_time",
                            tags=[str(x) for x in (raw.get("skills") or raw.get("jobLabels") or [])],
                            salary_min=salary_min,
                            salary_max=salary_max,
                            salary_period=salary_period,
                            education=str(raw.get("jobDegree") or "") or None,
                            experience=str(raw.get("jobExperience") or "") or None,
                            industry=str(raw.get("brandIndustry") or "") or None,
                            url=detail_url,
                            application_url=detail_url,
                        )
                    )
                    if len(result.jobs) >= self.max_jobs:
                        return result
            except Exception as exc:
                result.status = "partial" if result.jobs else "failed"
                result.warnings.append(f"采集失败：{type(exc).__name__}: {exc}")
        if not result.jobs and result.status == "success":
            result.status = "empty"
        return result
