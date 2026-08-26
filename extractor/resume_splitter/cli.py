from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parser import ResumeParser


COMPONENT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = COMPONENT_ROOT.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拆解 PDF、Word、LaTeX、Markdown 简历并保存到本地")
    parser.add_argument("files", nargs="*", help="要解析的简历文件；省略时处理 inputs 目录")
    parser.add_argument(
        "-i",
        "--input-dir",
        default=str(PROJECT_ROOT / "inputs"),
        help="批量输入目录（默认: 项目根目录 inputs）",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(COMPONENT_ROOT / "outputs"),
        help="本地输出目录（默认: extractor/outputs）",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="递归扫描输入目录")
    parser.add_argument("--json", action="store_true", help="向标准输出打印完整 JSON（仅单文件时）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    component = ResumeParser()
    output_root = Path(args.output_dir)

    if args.files:
        failed = False
        for file_name in args.files:
            try:
                document, saved_to = component.parse_and_save(file_name, output_root)
                if args.json and len(args.files) == 1:
                    print(json.dumps(document.to_dict(), ensure_ascii=False, indent=2))
                else:
                    print(f"[ok] {file_name} -> {saved_to} ({len(document.sections)} 个栏目)")
                    for warning in document.warnings:
                        print(f"  [warning] {warning}")
            except Exception as exc:
                failed = True
                print(f"[error] {file_name}: {exc}", file=sys.stderr)
        return 1 if failed else 0

    try:
        records = component.parse_directory(args.input_dir, output_root, recursive=args.recursive)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    if not records:
        print(f"[warning] {args.input_dir} 中没有找到支持的简历文件")
        return 0
    for record in records:
        if record["status"] == "ok":
            print(f"[ok] {record['source']} -> {record['output']} ({record['section_count']} 个栏目)")
        else:
            print(f"[error] {record['source']}: {record['error']}", file=sys.stderr)
    return 1 if any(record["status"] == "error" for record in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
