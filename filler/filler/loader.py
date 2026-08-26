from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label}不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}不是有效 JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}必须是 JSON 对象")
    return data


def load_profile(path: Path) -> dict[str, Any]:
    data = load_json_object(path, "用户画像")
    if not isinstance(data.get("profile_id"), str) or not isinstance(data.get("identity"), dict):
        raise ValueError("用户画像缺少 profile_id 或 identity")
    return data


def load_selected_jobs(path: Path) -> dict[str, Any]:
    data = load_json_object(path, "待投递岗位表")
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("待投递岗位表必须包含 jobs 数组；请从 filter 页面导出 selected-jobs.json")
    if not jobs:
        raise ValueError("待投递岗位表中没有已选择岗位")
    if any(not isinstance(job, dict) for job in jobs):
        raise ValueError("jobs 中的每个岗位都必须是对象")
    return data


def find_latest_profile(project_root: Path) -> Path:
    candidates = list((project_root / "profile_builder" / "outputs").glob("*/profile.json"))
    if not candidates:
        raise FileNotFoundError("未找到 profile_builder 生成的 profile.json")
    return max(candidates, key=lambda path: path.stat().st_mtime)
