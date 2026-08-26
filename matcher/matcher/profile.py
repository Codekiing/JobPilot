from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_latest_profile(project_root: Path) -> Path:
    candidates = list((project_root / "profile_builder" / "outputs").glob("*/profile.json"))
    if not candidates:
        raise FileNotFoundError("未找到用户画像，请先运行 profile_builder 或使用 --profile 指定文件")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_profile(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("用户画像必须是 JSON 对象")
    required = {"profile_id", "target", "capabilities", "matching_config"}
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError(f"用户画像缺少字段：{', '.join(missing)}")
    return data


def employment_types(profile: dict[str, Any]) -> set[str]:
    return {str(value) for value in profile.get("target", {}).get("employment_types", [])}
