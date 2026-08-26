from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import MatchEngine
from .profile import find_latest_profile, load_profile
from .providers import (
    BossProvider,
    CompanyCareersProvider,
    ImportProvider,
    NowcoderProvider,
    OfferShowProvider,
    ShixisengProvider,
)
from .storage import save_run


SOURCE_NAMES = ("boss", "shixiseng", "nowcoder", "offershow")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据用户画像聚合并匹配招聘岗位（本地规则，不调用模型）")
    parser.add_argument("--profile", type=Path, help="profile_builder 生成的 profile.json；默认读取最新结果")
    parser.add_argument("--output", type=Path, default=Path("matcher/outputs"), help="本地输出根目录")
    parser.add_argument("--sources", default=",".join(SOURCE_NAMES), help="逗号分隔的在线渠道")
    parser.add_argument("--query", action="append", help="覆盖画像自动生成的检索词，可重复传入")
    parser.add_argument("--max-per-source", type=int, default=30, help="每个渠道最多采集条数")
    parser.add_argument("--limit", type=int, default=100, help="最终最多输出条数")
    parser.add_argument("--min-score", type=float, default=0, help="最低匹配分")
    parser.add_argument("--timeout", type=float, default=15, help="单次网络请求超时秒数")
    parser.add_argument("--offline", action="store_true", help="不访问在线渠道，仅处理导入文件")
    parser.add_argument("--import-jobs", type=Path, action="append", default=[], help="导入 JSON/CSV 岗位，可重复")
    parser.add_argument("--career-url", action="append", default=[], help="含 JobPosting JSON-LD 的公司招聘官网，可重复")
    parser.add_argument("--json", action="store_true", help="在终端输出完整 JSON")
    return parser


def _providers(args) -> list:
    kwargs = {"timeout": args.timeout, "max_jobs": max(1, args.max_per_source)}
    providers = []
    if args.import_jobs:
        providers.append(ImportProvider(args.import_jobs, **kwargs))
    if args.career_url and not args.offline:
        providers.append(CompanyCareersProvider(args.career_url, **kwargs))
    if not args.offline:
        selected = {value.strip() for value in args.sources.split(",") if value.strip()}
        unknown = selected - set(SOURCE_NAMES)
        if unknown:
            raise ValueError("未知渠道：" + ", ".join(sorted(unknown)))
        mapping = {
            "boss": BossProvider,
            "shixiseng": ShixisengProvider,
            "nowcoder": NowcoderProvider,
            "offershow": OfferShowProvider,
        }
        providers.extend(mapping[name](**kwargs) for name in SOURCE_NAMES if name in selected)
    if not providers:
        raise ValueError("没有可用渠道；请移除 --offline 或提供 --import-jobs")
    return providers


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()
    profile_path = (args.profile or find_latest_profile(root)).expanduser().resolve()
    profile = load_profile(profile_path)
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        providers = _providers(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    run = MatchEngine(providers).run(
        profile,
        queries=args.query,
        min_score=max(0, args.min_score),
        limit=max(1, args.limit),
    )
    saved_to = save_run(run, output.resolve())
    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"画像：{profile_path}")
        print(f"检索词：{'；'.join(run.queries)}")
        print(f"岗位：采集 {run.raw_job_count} 条，去重 {run.deduplicated_job_count} 条，输出 {len(run.jobs)} 条")
        for provider in run.providers:
            print(f"- {provider.source}: {provider.status}, {len(provider.jobs)} 条")
            for warning in provider.warnings:
                print(f"  {warning}")
        print(f"结果：{saved_to}")
    return 0
