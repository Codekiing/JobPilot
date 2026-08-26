from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .limits import load_limit_config, resolve_quota
from .models import JobGroup
from .template import render_html


def find_latest_jobs(project_root: Path) -> Path:
    candidates = list((project_root / "matcher" / "outputs").glob("*/*/jobs.json"))
    if not candidates:
        raise FileNotFoundError("未找到 matcher 生成的 jobs.json，请先运行第三组件或使用 --input 指定文件")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_match_table(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("输入必须是 matcher 生成且包含 jobs 数组的 JSON 汇总表")
    return data


def _job_key(job: dict[str, Any]) -> str:
    source = str(job.get("source") or "unknown")
    source_id = str(job.get("source_job_id") or "")
    if source_id:
        return f"{source}:{source_id}"
    raw = f"{source}|{job.get('company')}|{job.get('title')}|{job.get('url')}"
    return f"{source}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _compact_job(job: dict[str, Any]) -> dict[str, Any]:
    match = job.get("match") if isinstance(job.get("match"), dict) else {}
    salary_min, salary_max = job.get("salary_min"), job.get("salary_max")
    salary = ""
    if salary_min is not None or salary_max is not None:
        amounts = [str(value) for value in (salary_min, salary_max) if value is not None]
        period = {"month": "月", "day": "天", "year": "年"}.get(job.get("salary_period"), job.get("salary_period") or "")
        salary = f"{'-'.join(amounts)} {job.get('salary_currency', 'CNY')}/{period}".rstrip("/")
    return {
        "job_key": _job_key(job),
        "source": str(job.get("source") or ""),
        "source_job_id": str(job.get("source_job_id") or ""),
        "title": str(job.get("title") or "未命名岗位"),
        "company": str(job.get("company") or "未知公司"),
        "locations": [str(value) for value in job.get("locations", [])],
        "employment_type": str(job.get("employment_type") or "unknown"),
        "salary": salary,
        "education": str(job.get("education") or ""),
        "experience": str(job.get("experience") or ""),
        "source_url": str(job.get("url") or ""),
        "application_url": str(job.get("application_url") or job.get("url") or ""),
        "published_at": str(job.get("published_at") or ""),
        "deadline": str(job.get("deadline") or ""),
        "score": float(match.get("total") or 0),
        "grade": str(match.get("grade") or ""),
        "hard_constraints_passed": bool(match.get("hard_constraints_passed", True)),
        "matched_skills": [str(value) for value in match.get("matched_skills", [])],
        "reasons": [str(value) for value in match.get("reasons", [])],
        "warnings": [str(value) for value in match.get("warnings", [])],
        **{
            key: job[key]
            for key in (
                "application_limit",
                "application_limit_confirmed",
                "application_limit_source_url",
                "application_limit_verified_at",
            )
            if key in job
        },
    }


class FilterBuilder:
    def __init__(self, limit_config: dict[str, Any] | None = None) -> None:
        self.limit_config = limit_config or load_limit_config(None)

    @classmethod
    def from_limit_file(cls, path: Path | None) -> "FilterBuilder":
        return cls(load_limit_config(path))

    def build_data(self, table: dict[str, Any], source_path: Path) -> dict[str, Any]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for raw in table.get("jobs", []):
            if not isinstance(raw, dict):
                continue
            job = _compact_job(raw)
            key = (job["company"], job["employment_type"])
            groups.setdefault(key, []).append(job)

        output_groups: list[JobGroup] = []
        for (company, employment_type), jobs in groups.items():
            jobs.sort(key=lambda item: item["score"], reverse=True)
            group_hash = hashlib.sha1(f"{company}|{employment_type}".encode("utf-8")).hexdigest()[:12]
            output_groups.append(
                JobGroup(
                    group_id=f"group-{group_hash}",
                    company=company,
                    employment_type=employment_type,
                    quota=resolve_quota(company, employment_type, jobs, self.limit_config),
                    jobs=jobs,
                )
            )
        output_groups.sort(key=lambda group: max((job["score"] for job in group.jobs), default=0), reverse=True)
        input_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        filter_id = "filter-" + hashlib.sha1(f"{input_hash}|{created_at}".encode("utf-8")).hexdigest()[:16]
        confirmed_count = sum(1 for group in output_groups if group.quota.confirmed)
        reviewed_undisclosed_count = sum(
            1 for group in output_groups if group.quota.verification_status == "public_not_found"
        )
        return {
            "schema_version": "1.0",
            "component": "filter",
            "component_version": "0.1.0",
            "filter_id": filter_id,
            "profile_id": str(table.get("profile_id") or "unknown"),
            "created_at": created_at,
            "source_matcher_json": str(source_path.resolve()),
            "source_matcher_sha256": input_hash,
            "source_created_at": str(table.get("created_at") or ""),
            "summary": {
                "job_count": sum(len(group.jobs) for group in output_groups),
                "company_count": len({group.company for group in output_groups}),
                "quota_group_count": len(output_groups),
                "confirmed_quota_count": confirmed_count,
                "reviewed_undisclosed_quota_count": reviewed_undisclosed_count,
                "resolved_quota_count": confirmed_count + reviewed_undisclosed_count,
            },
            "groups": [group.to_dict() for group in output_groups],
        }

    def build_file(self, input_path: Path, output_path: Path) -> dict[str, Any]:
        table = load_match_table(input_path)
        data = self.build_data(table, input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_html(data), encoding="utf-8")
        return data
