from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from ..models import Job, ProviderResult
from .base import Provider


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [x.strip() for x in str(value or "").replace("|", ",").split(",") if x.strip()]


class ImportProvider(Provider):
    name = "import"

    def __init__(self, paths: list[Path], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.paths = paths

    def _records(self, path: Path) -> list[dict[str, Any]]:
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("jobs", data.get("data", []))
        if not isinstance(data, list):
            raise ValueError("JSON 导入文件必须是数组，或包含 jobs/data 数组")
        return [row for row in data if isinstance(row, dict)]

    def _job(self, row: dict[str, Any], path: Path) -> Job | None:
        title = str(row.get("title") or row.get("job_title") or row.get("职位") or "").strip()
        if not title:
            return None
        company = str(row.get("company") or row.get("公司") or "").strip()
        url = str(row.get("url") or row.get("岗位链接") or row.get("投递链接") or "").strip()
        source = str(row.get("source") or row.get("渠道") or f"import:{path.stem}")
        source_id = str(row.get("source_job_id") or row.get("job_id") or "")
        if not source_id:
            source_id = hashlib.sha1(f"{title}|{company}|{url}".encode("utf-8")).hexdigest()[:16]
        return Job(
            source=source,
            source_job_id=source_id,
            title=title,
            company=company,
            locations=_list(row.get("locations") or row.get("location") or row.get("地点")),
            employment_type=str(row.get("employment_type") or row.get("岗位类型") or "unknown"),
            description=str(row.get("description") or row.get("岗位描述") or ""),
            requirements=str(row.get("requirements") or row.get("岗位要求") or ""),
            tags=_list(row.get("tags") or row.get("技能标签")),
            education=str(row.get("education") or row.get("学历") or "") or None,
            experience=str(row.get("experience") or row.get("经验") or "") or None,
            industry=str(row.get("industry") or row.get("行业") or "") or None,
            published_at=str(row.get("published_at") or row.get("发布时间") or "") or None,
            deadline=str(row.get("deadline") or row.get("截止时间") or "") or None,
            url=url,
            application_url=str(row.get("application_url") or row.get("投递链接") or url),
        )

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        if not self.paths:
            return ProviderResult(source=self.name, status="skipped", queries=queries)
        result = ProviderResult(source=self.name, status="success", queries=queries)
        for path in self.paths:
            try:
                for row in self._records(path):
                    job = self._job(row, path)
                    if job:
                        result.jobs.append(job)
            except Exception as exc:
                result.status = "partial" if result.jobs else "failed"
                result.warnings.append(f"{path}: {type(exc).__name__}: {exc}")
        if len(result.jobs) > self.max_jobs:
            result.jobs = result.jobs[: self.max_jobs]
        return result
