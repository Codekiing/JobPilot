from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Quota


def load_limit_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema_version": "1.0", "default_limit": 1, "aliases": {}, "companies": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("公司投递限额配置必须是 JSON 对象")
    default_limit = data.get("default_limit", 1)
    if not isinstance(default_limit, int) or default_limit < 1:
        raise ValueError("default_limit 必须是大于 0 的整数")
    if not isinstance(data.get("companies", {}), dict):
        raise ValueError("companies 必须是对象")
    if not isinstance(data.get("aliases", {}), dict):
        raise ValueError("aliases 必须是对象")
    return data


def _canonical_company(company: str, config: dict[str, Any]) -> str:
    aliases = config.get("aliases", {})
    return str(aliases.get(company, company)).strip()


def _rules_for(company: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("companies", {}).get(_canonical_company(company, config), [])
    if isinstance(raw, dict):
        return [raw]
    return [rule for rule in raw if isinstance(rule, dict)] if isinstance(raw, list) else []


def resolve_quota(
    company: str,
    employment_type: str,
    jobs: list[dict[str, Any]],
    config: dict[str, Any],
) -> Quota:
    embedded = {
        int(job["application_limit"])
        for job in jobs
        if isinstance(job.get("application_limit"), int) and int(job["application_limit"]) > 0
    }
    if embedded:
        limit = min(embedded)
        confirmed = all(bool(job.get("application_limit_confirmed", True)) for job in jobs if job.get("application_limit"))
        return Quota(
            limit=limit,
            confirmed=confirmed,
            source="job_data",
            verification_status="confirmed" if confirmed else "unverified",
            source_url=next((str(job.get("application_limit_source_url")) for job in jobs if job.get("application_limit_source_url")), ""),
            verified_at=next((str(job.get("application_limit_verified_at")) for job in jobs if job.get("application_limit_verified_at")), ""),
            note="岗位数据内置限额" if len(embedded) == 1 else "岗位数据存在多个限额，采用较小值",
        )

    for rule in _rules_for(company, config):
        types = [str(value) for value in rule.get("employment_types", [])]
        if types and employment_type not in types:
            continue
        limit = rule.get("limit")
        if not isinstance(limit, int) or limit < 1:
            continue
        return Quota(
            limit=limit,
            confirmed=bool(rule.get("confirmed", False)),
            source="company_config",
            verification_status=str(
                rule.get("verification_status")
                or ("confirmed" if rule.get("confirmed", False) else "unverified")
            ),
            source_url=str(rule.get("source_url") or ""),
            verified_at=str(rule.get("verified_at") or ""),
            note=str(rule.get("note") or ""),
        )

    return Quota(
        limit=int(config.get("default_limit", 1)),
        confirmed=False,
        source="conservative_default",
        verification_status="unverified",
        note="未找到可靠规则，暂按 1 个处理；请在页面中核对并确认",
    )
