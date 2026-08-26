from __future__ import annotations

import argparse
import json
from pathlib import Path

from .browser import BrowserDependencyError, execute_plan
from .loader import find_latest_profile, load_profile, load_selected_jobs
from .official_sites import load_official_sites
from .planner import FillPlanner
from .storage import save_plan


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据用户画像和待投递岗位生成填表草稿；默认不打开网站")
    parser.add_argument("--profile", type=Path, help="profile_builder 生成的 profile.json；默认读取最新结果")
    parser.add_argument("--jobs", type=Path, default=Path("filler/inputs/selected-jobs.json"), help="filter 页面导出的 selected-jobs.json")
    parser.add_argument("--output", type=Path, default=Path("filler/outputs"), help="本地草稿输出目录")
    parser.add_argument("--execute", action="store_true", help="打开浏览器并逐岗位确认后填充；永不自动提交")
    parser.add_argument("--headless", action="store_true", help="无界面浏览器模式；登录场景不推荐")
    parser.add_argument("--local-draft-only", action="store_true", help="填入后不询问是否点击网站的保存草稿/暂存按钮")
    parser.add_argument("--save-remote-draft", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--browser-profile", type=Path, default=Path("filler/.browser-profile"), help="独立浏览器登录状态目录")
    parser.add_argument("--official-sites", type=Path, default=Path("filler/config/official_sites.json"), help="公司官方招聘入口配置")
    return parser


def _resolve(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()
    profile_path = _resolve(root, args.profile) if args.profile else find_latest_profile(root)
    jobs_path = _resolve(root, args.jobs)
    output_root = _resolve(root, args.output)
    profile = load_profile(profile_path)
    selected_jobs = load_selected_jobs(jobs_path)
    official_sites_path = _resolve(root, args.official_sites)
    official_sites = load_official_sites(official_sites_path)
    plan = FillPlanner(official_sites).build(
        profile, selected_jobs, profile_path=profile_path, selected_jobs_path=jobs_path
    )
    run_dir = save_plan(plan, output_root)
    print(f"画像：{profile_path}")
    print(f"岗位：{len(plan.applications)} 个")
    print(f"草稿：{run_dir / 'fill-plan.json'}")
    print(f"官网配置：{official_sites_path}")
    if plan.missing_required_fields:
        print("缺少必要字段：" + "、".join(plan.missing_required_fields))
    if not args.execute:
        print("模式：local_draft_only（未打开招聘网站、未发送个人信息）")
        return 0
    try:
        reports = execute_plan(
            plan.to_dict(),
            run_dir=run_dir,
            browser_profile=_resolve(root, args.browser_profile),
            headless=args.headless,
            save_remote_draft=not args.local_draft_only,
        )
    except BrowserDependencyError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"填充报告：{len(reports)} 份；未自动提交任何申请")
    return 0
