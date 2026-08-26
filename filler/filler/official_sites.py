from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class OfficialSiteResolution:
    url: str
    source: str
    company_key: str
    note: str = ""


def load_official_sites(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"公司官网配置不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"公司官网配置不是有效 JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("companies"), dict):
        raise ValueError("公司官网配置必须包含 companies 对象")
    return data


def _normalized_company(value: str) -> str:
    return re.sub(r"[\s·•（）()\-_]+", "", value).casefold()


def _valid_http_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def resolve_official_site(
    company: str,
    employment_type: str,
    original_url: str,
    config: dict[str, Any] | None,
) -> OfficialSiteResolution:
    config = config or {"companies": {}, "aliases": {}}
    aliases = config.get("aliases") if isinstance(config.get("aliases"), dict) else {}
    companies = config.get("companies") if isinstance(config.get("companies"), dict) else {}

    lookup = {_normalized_company(str(key)): str(key) for key in companies}
    alias_lookup = {_normalized_company(str(key)): str(value) for key, value in aliases.items()}
    requested = company.strip()
    canonical = alias_lookup.get(_normalized_company(requested), requested)
    company_key = lookup.get(_normalized_company(canonical), canonical)
    entry = companies.get(company_key)
    if isinstance(entry, dict):
        candidate = _valid_http_url(entry.get(employment_type) or entry.get("default"))
        if candidate:
            source = "verified_company_config"
            return OfficialSiteResolution(candidate, source, company_key, str(entry.get("note") or ""))

    return OfficialSiteResolution("", "official_site_not_found", company_key)
