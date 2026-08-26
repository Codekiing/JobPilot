from __future__ import annotations

import argparse
from pathlib import Path

from .builder import FilterBuilder, find_latest_jobs
from .storage import output_path, update_manifest


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据岗位汇总表生成可交互的最终投递岗位筛选页面")
    parser.add_argument("--input", type=Path, help="matcher 生成的 jobs.json；默认读取最新结果")
    parser.add_argument("--limits", type=Path, default=Path("filter/config/company_limits.json"), help="公司投递限额配置")
    parser.add_argument("--output", type=Path, default=Path("filter/outputs"), help="输出根目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()
    input_path = (args.input if args.input and args.input.is_absolute() else root / args.input) if args.input else find_latest_jobs(root)
    limit_path = args.limits if args.limits.is_absolute() else root / args.limits
    output_root = args.output if args.output.is_absolute() else root / args.output
    builder = FilterBuilder.from_limit_file(limit_path if limit_path.exists() else None)
    table = __import__("json").loads(input_path.read_text(encoding="utf-8"))
    profile_id = str(table.get("profile_id") or "unknown")
    html_path = output_path(output_root.resolve(), profile_id)
    data = builder.build_file(input_path.resolve(), html_path)
    update_manifest(output_root.resolve(), html_path, data)
    print(f"输入：{input_path.resolve()}")
    print(f"岗位：{data['summary']['job_count']} 条，{data['summary']['company_count']} 家公司")
    print(
        "限额："
        f"明确规则 {data['summary']['confirmed_quota_count']} 组，"
        f"已核查但官方未披露 {data['summary']['reviewed_undisclosed_quota_count']} 组，"
        f"共核查 {data['summary']['resolved_quota_count']}/{data['summary']['quota_group_count']} 组"
    )
    print(f"页面：{html_path}")
    return 0
