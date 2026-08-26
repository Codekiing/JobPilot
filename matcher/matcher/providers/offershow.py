from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from ..http import request_json
from ..models import Job, ProviderResult
from .base import Provider


def _date(value: Any) -> str | None:
    text = str(value or "")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return None


def _published(value: Any) -> str | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return None


def _tokens(queries: list[str]) -> list[str]:
    values: list[str] = []
    for query in queries:
        values.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9+.#-]+", query))
    expanded: list[str] = []
    for value in values:
        expanded.append(value)
        for term in ("大模型", "算法", "后训练", "强化学习", "多模态", "Agent", "RLHF", "LLM"):
            if term.lower() in value.lower():
                expanded.append(term)
    return list(dict.fromkeys(expanded))


class OfferShowProvider(Provider):
    name = "offershow"
    endpoint = "https://offershow.cn/api/od/get_recruit_column?page=1&size=100"

    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        result = ProviderResult(
            source=self.name,
            status="success",
            queries=queries,
            discovery_urls=["https://offershow.cn/jobs/homepage"],
        )
        try:
            response = request_json(
                self.endpoint,
                timeout=self.timeout,
                method="POST",
                form={"id": 0, "filter_type": 0},
                headers={"Referer": "https://offershow.cn/jobs/homepage"},
            )
            if response.get("code") != 200001:
                raise RuntimeError(response.get("msg") or f"响应码 {response.get('code')}")
            terms = _tokens(queries)
            plans = (response.get("data") or {}).get("data", [])
            for plan in plans:
                positions = [line.strip(" ·、") for line in str(plan.get("positions", "")).splitlines() if line.strip()]
                for position in positions:
                    haystack = f"{position} {plan.get('title', '')} {plan.get('company_name', '')}".lower()
                    if terms and not any(term.lower() in haystack for term in terms):
                        continue
                    plan_id = str(plan.get("uuid") or plan.get("object_uuid") or "")
                    suffix = hashlib.sha1(position.encode("utf-8")).hexdigest()[:10]
                    notice_url = str(plan.get("notice_url") or "")
                    recruit_title = str(plan.get("title") or "")
                    employment = "internship" if "实习" in recruit_title else "campus" if "校招" in recruit_title else "full_time"
                    locations = [x.strip() for x in re.split(r"\s*[|/]\s*", str(plan.get("city") or "")) if x.strip()]
                    result.jobs.append(
                        Job(
                            source=self.name,
                            source_job_id=f"{plan_id}:{suffix}",
                            title=position,
                            company=str(plan.get("company_name") or ""),
                            locations=locations,
                            employment_type=employment,
                            description=recruit_title,
                            published_at=_published(plan.get("release_time")),
                            deadline=_date(plan.get("end_time")),
                            url="https://offershow.cn/jobs/homepage",
                            application_url=notice_url or "https://offershow.cn/jobs/homepage",
                            source_payload={"recruit_plan_id": plan_id, "official": bool(plan.get("is_official"))},
                        )
                    )
                    if len(result.jobs) >= self.max_jobs:
                        return result
        except Exception as exc:
            result.status = "failed"
            result.warnings.append(f"采集失败：{type(exc).__name__}: {exc}")
        if not result.jobs and result.status == "success":
            result.status = "empty"
        return result
