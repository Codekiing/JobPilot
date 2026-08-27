from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .mapper import build_draft_fields, build_structured_records
from .models import ApplicationDraft, FillPlan
from .official_sites import resolve_official_site


REQUIRED_FIELDS = ("full_name", "email", "phone")
SUPPORTED_RESUME_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".html"}


def adapter_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("mokahr.com"):
        return "moka"
    if host.endswith("jobs.feishu.cn"):
        return "feishu"
    if host.endswith("zhiye.com"):
        return "beisen"
    if host.endswith("hotjob.cn"):
        return "hotjob"
    if host.endswith("nowcoder.com"):
        return "nowcoder"
    if host.endswith("sensetime.com"):
        return "atsx"
    return "generic"


def _valid_application_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


class FillPlanner:
    def __init__(self, official_sites: dict[str, Any] | None = None) -> None:
        self.official_sites = official_sites

    def build(
        self,
        profile: dict[str, Any],
        selected_jobs: dict[str, Any],
        *,
        profile_path: Path,
        selected_jobs_path: Path,
        resume_file: Path | None = None,
    ) -> FillPlan:
        profile_id = str(profile.get("profile_id") or "")
        selected_profile_id = str(selected_jobs.get("profile_id") or "")
        if selected_profile_id and selected_profile_id != profile_id:
            raise ValueError(
                f"用户画像与待投递岗位不属于同一画像: {profile_id} != {selected_profile_id}"
            )

        resolved_resume = _resolve_resume_file(resume_file)
        fields = build_draft_fields(profile)
        available = {field.key for field in fields}
        missing = [key for key in REQUIRED_FIELDS if key not in available]
        applications: list[ApplicationDraft] = []
        seen: set[str] = set()
        for index, job in enumerate(selected_jobs.get("jobs", []), start=1):
            original_url = _valid_application_url(job.get("application_url") or job.get("source_url") or job.get("url"))
            job_key = str(job.get("job_key") or f"selected-{index}")
            dedupe_key = f"{job_key}|{original_url}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            title = str(job.get("title") or "未命名岗位")
            company = str(job.get("company") or "未知公司")
            employment_type = str(job.get("employment_type") or job.get("job_type") or "default")
            resolution = resolve_official_site(company, employment_type, original_url, self.official_sites)
            url = resolution.url
            warnings: list[str] = []
            if not url:
                warnings.append("未能确认公司官方招聘入口，已禁止浏览器填充；请补充 official_sites.json")
            if resolution.note:
                warnings.append(resolution.note)
            if missing:
                warnings.append("画像缺少必要字段：" + "、".join(missing))
            raw_id = f"{profile_id}|{job_key}|{original_url}|{url}"
            applications.append(
                ApplicationDraft(
                    draft_id="draft-" + hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16],
                    job_key=job_key,
                    company=company,
                    title=title,
                    application_url=url,
                    original_application_url=original_url,
                    official_url_source=resolution.source,
                    source_url=str(job.get("source_url") or job.get("url") or ""),
                    adapter=adapter_for(url),
                    warnings=warnings,
                )
            )

        created_at = datetime.now(timezone.utc).isoformat()
        plan_raw = f"{profile_id}|{selected_jobs_path.resolve()}|{created_at}"
        return FillPlan(
            plan_id="fill-" + hashlib.sha1(plan_raw.encode("utf-8")).hexdigest()[:16],
            profile_id=profile_id,
            created_at=created_at,
            source_profile_json=str(profile_path.resolve()),
            source_selected_jobs_json=str(selected_jobs_path.resolve()),
            resume_file=str(resolved_resume) if resolved_resume else None,
            fields=fields,
            structured_records=build_structured_records(profile),
            applications=applications,
            missing_required_fields=missing,
            safety={
                "browser_execution_default": False,
                "sensitive_data_confirmation_required": True,
                "remote_draft_save_default": True,
                "resume_upload_default": False,
                "resume_upload_confirmation_required": True,
                "automatic_submit": False,
                "local_draft_contains_personal_data": True,
            },
        )


def _resolve_resume_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"简历文件不存在: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_RESUME_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_RESUME_SUFFIXES))
        raise ValueError(f"不支持的简历文件格式: {resolved.suffix or '无扩展名'}；支持 {allowed}")
    return resolved
