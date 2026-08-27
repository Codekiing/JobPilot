from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urljoin

from ..models import Job, ProviderResult
from .base import Provider


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


class BrowserOfficialProvider(Provider):
    """Render official career pages whose positions are loaded by JavaScript.

    This provider is deliberately limited to sites with stable, identifiable
    position-card structures. If Playwright or Chromium is unavailable, it
    reports ``needs_browser`` and lets the company-focused public fallback run.
    """

    name = "official_browser"
    priority = 15
    source_kind = "official"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.discovery_urls = {
            "字节跳动": "https://jobs.bytedance.com/campus/position",
            "美团": "https://zhaopin.meituan.com/web/position",
        }

    def _bytedance_job(self, text: str, href: str) -> Job | None:
        values = _lines(text)
        if not values or not href:
            return None
        match = re.search(r"/position/(\d+)/detail", href)
        source_id = match.group(1) if match else href
        employment = "internship" if any("实习" in value for value in values[1:5]) else "campus"
        return Job(
            source=self.name,
            source_job_id=source_id,
            title=values[0],
            company="字节跳动",
            locations=re.split(r"[、,，]|等\s*\d+\s*个城市", values[1]) if len(values) > 1 else [],
            employment_type=employment,
            description=" ".join(values[5:]),
            tags=[values[3]] if len(values) > 3 else [],
            url=urljoin(self.discovery_urls["字节跳动"], href),
            application_url=urljoin(self.discovery_urls["字节跳动"], href),
            source_kind="official",
            discovered_from=self.discovery_urls["字节跳动"],
            application_source="official",
        )

    def _meituan_job(self, source_id: str, title: str, facts: list[str], descriptions: list[str]) -> Job | None:
        if not source_id or not title:
            return None
        employment_label = facts[0] if facts else ""
        employment = "internship" if "实习" in employment_label else "campus" if "校招" in employment_label else "full_time"
        location = facts[1] if len(facts) > 1 else ""
        detail_url = "https://zhaopin.meituan.com/web/position/detail?" + urlencode({"jobUnionId": source_id})
        return Job(
            source=self.name,
            source_job_id=source_id,
            title=title,
            company="美团",
            locations=[part for part in re.split(r"[、,，]", location) if part],
            employment_type=employment,
            description=" ".join(descriptions),
            published_at=facts[2].removeprefix("更新于") if len(facts) > 2 else None,
            tags=[facts[3]] if len(facts) > 3 else [],
            url=detail_url,
            application_url=detail_url,
            source_kind="official",
            discovered_from=self.discovery_urls["美团"],
            application_source="official",
        )

    def _collect_bytedance(self, page: Any, queries: list[str], limit: int | None = None) -> list[Job]:
        limit = limit or self.max_jobs
        jobs: list[Job] = []
        seen: set[str] = set()
        for query in queries[:4]:
            url = self.discovery_urls["字节跳动"] + "?" + urlencode({"keywords": query, "current": 1, "limit": 50})
            page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
            page.wait_for_timeout(1200)
            cards = page.locator('a[href*="/campus/position/"][href$="/detail"]')
            for index in range(min(cards.count(), 50)):
                card = cards.nth(index)
                job = self._bytedance_job(card.inner_text(), card.get_attribute("href") or "")
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
                    if len(jobs) >= limit:
                        return jobs
        return jobs

    def _collect_meituan(self, page: Any, queries: list[str], limit: int | None = None) -> list[Job]:
        limit = limit or self.max_jobs
        page.goto(self.discovery_urls["美团"], wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
        page.wait_for_selector('input[placeholder*="关键词"]', timeout=int(self.timeout * 1000))
        jobs: list[Job] = []
        seen: set[str] = set()
        for query in queries[:4]:
            search = page.locator('input[placeholder*="关键词"]').first
            search.fill(query)
            search.press("Enter")
            page.wait_for_timeout(900)
            cards = page.locator('.position_list_item[data-jobunionid]')
            for index in range(min(cards.count(), 30)):
                card = cards.nth(index)
                source_id = card.get_attribute("data-jobunionid") or ""
                title = card.locator('.postion_name .title').first.inner_text()
                facts = card.locator('.split_line_box_item').all_inner_texts()
                descriptions = card.locator('.position_duty .desc').all_inner_texts()
                job = self._meituan_job(source_id, title, facts, descriptions)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
                    if len(jobs) >= limit:
                        return jobs
        return jobs

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        result = ProviderResult(
            source=self.name,
            status="success",
            queries=queries,
            discovery_urls=list(self.discovery_urls.values()),
            metadata={"phase": "official_dynamic", "planned_companies": len(self.discovery_urls)},
        )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result.status = "needs_browser"
            result.warnings.append("未安装 Playwright；已保留逐家大厂公开渠道补充")
            return result

        company_counts: dict[str, int] = {}
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                company_limit = max(1, self.max_jobs // len(self.discovery_urls))
                for company, collector in (
                    ("字节跳动", self._collect_bytedance),
                    ("美团", self._collect_meituan),
                ):
                    try:
                        company_jobs = collector(page, queries, company_limit)
                        result.jobs.extend(company_jobs)
                        company_counts[company] = len(company_jobs)
                    except Exception as exc:
                        company_counts[company] = 0
                        result.warnings.append(f"{company}: {type(exc).__name__}: {exc}")
                context.close()
                browser.close()
        except Exception as exc:
            result.status = "needs_browser"
            result.warnings.append(f"动态官网浏览器不可用：{type(exc).__name__}: {exc}")
            return result

        result.metadata["companies_with_jobs"] = sum(count > 0 for count in company_counts.values())
        result.metadata["company_job_counts"] = company_counts
        if result.warnings:
            result.status = "partial" if result.jobs else "failed"
        elif not result.jobs:
            result.status = "empty"
        return result
