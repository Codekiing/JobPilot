from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


TIER_ORDER = ("major", "mid_size", "unicorn", "growth")


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


@dataclass(frozen=True, slots=True)
class CompanyTarget:
    name: str
    tier: str
    career_urls: tuple[str, ...]
    aliases: tuple[str, ...] = ()


class CompanyCatalog:
    def __init__(self, companies: list[CompanyTarget]) -> None:
        self.companies = companies
        self._aliases: list[tuple[str, CompanyTarget]] = []
        for company in companies:
            for alias in (company.name, *company.aliases):
                normalized = _key(alias)
                if normalized:
                    self._aliases.append((normalized, company))
        self._aliases.sort(key=lambda item: len(item[0]), reverse=True)

    @classmethod
    def load(cls, path: Path) -> "CompanyCatalog":
        payload = json.loads(path.read_text(encoding="utf-8"))
        companies: list[CompanyTarget] = []
        for tier in TIER_ORDER:
            for item in payload.get("tiers", {}).get(tier, []):
                companies.append(
                    CompanyTarget(
                        name=str(item["name"]),
                        tier=tier,
                        career_urls=tuple(str(url) for url in item.get("career_urls", []) if str(url).strip()),
                        aliases=tuple(str(alias) for alias in item.get("aliases", []) if str(alias).strip()),
                    )
                )
        return cls(companies)

    def selected(self, tiers: list[str] | None = None) -> list[CompanyTarget]:
        selected = set(tiers or TIER_ORDER)
        return [company for company in self.companies if company.tier in selected]

    def identify(self, company_name: str) -> CompanyTarget | None:
        normalized = _key(company_name)
        if not normalized:
            return None
        for alias, company in self._aliases:
            if alias in normalized or normalized in alias:
                return company
        return None

    def classify(self, company_name: str) -> str:
        target = self.identify(company_name)
        return target.tier if target else "small_business"

    def canonical_name(self, company_name: str) -> str:
        target = self.identify(company_name)
        return target.name if target else company_name.strip()

    def is_official_application_url(self, company_name: str, url: str) -> bool:
        target = self.identify(company_name)
        host = (urlparse(url).hostname or "").lower()
        if not target or not host:
            return False
        for career_url in target.career_urls:
            official_host = (urlparse(career_url).hostname or "").lower()
            if official_host and (host == official_host or host.endswith(f".{official_host}")):
                return True
        return False

    def coverage(self, jobs: list[Any], *, tiers: list[str] | None = None) -> dict[str, Any]:
        targets = self.selected(tiers)
        represented: set[str] = set()
        for job in jobs:
            target = self.identify(str(getattr(job, "company", "")))
            if target:
                represented.add(target.name)
        by_tier: dict[str, dict[str, int]] = {}
        for tier in TIER_ORDER:
            planned = [target for target in targets if target.tier == tier]
            if not planned:
                continue
            by_tier[tier] = {
                "planned_companies": len(planned),
                "companies_with_jobs": sum(target.name in represented for target in planned),
            }
        return {
            "planned_companies": len(targets),
            "companies_with_jobs": len({target.name for target in targets if target.name in represented}),
            "by_tier": by_tier,
        }


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "company_catalog.json"


def load_default_catalog() -> CompanyCatalog:
    return CompanyCatalog.load(default_catalog_path())
