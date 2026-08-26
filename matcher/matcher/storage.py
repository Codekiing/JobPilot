from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .engine import MatchRun


CSV_FIELDS = [
    "排名",
    "匹配分",
    "等级",
    "硬约束通过",
    "岗位",
    "公司",
    "地点",
    "岗位类型",
    "薪资",
    "学历",
    "经验",
    "命中技能",
    "匹配理由",
    "渠道",
    "发布时间",
    "截止时间",
    "岗位链接",
    "投递链接",
]


def _salary(job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return ""
    values = [value for value in (job.salary_min, job.salary_max) if value is not None]
    amount = "-".join(f"{value:g}" for value in values)
    period = {"month": "月", "day": "天", "year": "年"}.get(job.salary_period, job.salary_period or "")
    return f"{amount} {job.salary_currency}/{period}".strip("/")


def _rows(run: MatchRun):
    for rank, item in enumerate(run.jobs, start=1):
        job, match = item.job, item.match
        yield {
            "排名": rank,
            "匹配分": match.total,
            "等级": match.grade,
            "硬约束通过": "是" if match.hard_constraints_passed else "否",
            "岗位": job.title,
            "公司": job.company,
            "地点": "、".join(job.locations),
            "岗位类型": job.employment_type,
            "薪资": _salary(job),
            "学历": job.education or "",
            "经验": job.experience or "",
            "命中技能": "、".join(match.matched_skills),
            "匹配理由": "；".join(match.reasons + match.warnings),
            "渠道": job.source,
            "发布时间": job.published_at or "",
            "截止时间": job.deadline or "",
            "岗位链接": job.url,
            "投递链接": job.application_url,
        }


def save_run(run: MatchRun, output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / run.profile_id / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = run.to_dict()
    (run_dir / "jobs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = list(_rows(run))
    with (run_dir / "jobs.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        f"# 岗位匹配汇总（{run.profile_id}）",
        "",
        f"生成时间：{run.created_at}",
        f"检索词：{'；'.join(run.queries)}",
        f"共采集 {run.raw_job_count} 条，去重后 {run.deduplicated_job_count} 条，输出 {len(run.jobs)} 条。",
        "",
        "| 排名 | 匹配分 | 岗位 | 公司 | 地点 | 类型 | 渠道 | 投递 |",
        "|---:|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        apply_url = str(row["投递链接"] or row["岗位链接"])
        link = f"[打开]({apply_url})" if apply_url else ""
        safe = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['排名']} | {row['匹配分']} | {safe(row['岗位'])} | {safe(row['公司'])} | "
            f"{safe(row['地点'])} | {safe(row['岗位类型'])} | {safe(row['渠道'])} | {link} |"
        )
    lines.extend(["", "## 渠道状态", ""])
    for provider in run.providers:
        warning = "；".join(provider.warnings)
        lines.append(f"- {provider.source}: `{provider.status}`，{len(provider.jobs)} 条" + (f"；{warning}" if warning else ""))
    (run_dir / "jobs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest_path = output_root / "manifest.json"
    manifest = {"latest": str(run_dir.resolve()), "profile_id": run.profile_id, "created_at": run.created_at}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir
