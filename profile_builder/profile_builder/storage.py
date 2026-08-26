from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import UserProfile


def save_profile(profile: UserProfile, questions: list[object], output_root: str | Path) -> Path:
    output_root = Path(output_root).expanduser().resolve()
    name = _safe_name(str(profile.identity.get("name") or "candidate"))
    profile_dir = output_root / f"{name}-{profile.profile_id.removeprefix('profile-')[:8]}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(profile_dir / "profile.json", json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n")
    question_payload = {
        "schema_version": "1.0",
        "profile_id": profile.profile_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "completion": profile.completion,
        "survey_answers": profile.questionnaire.get("survey_answers", {}),
        "questions": [question.to_dict() for question in questions if hasattr(question, "to_dict")],
    }
    _atomic_write(profile_dir / "questions.json", json.dumps(question_payload, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(profile_dir / "profile_summary.md", _render_summary(profile))
    return profile_dir


def _render_summary(profile: UserProfile) -> str:
    skills = ", ".join(item["name"] for item in profile.capabilities.get("skills", [])) or "待补充"
    roles = ", ".join(profile.target.get("primary_roles", [])) or "待补充"
    locations = ", ".join(profile.target.get("preferred_locations", [])) or "待补充"
    missing = profile.completion.get("missing_required", [])
    missing_text = "、".join(item["label"] for item in missing) or "无"
    return (
        f"# {profile.identity.get('name') or '候选人'}的求职画像\n\n"
        f"- 画像 ID：`{profile.profile_id}`\n"
        f"- 完成度：{profile.completion.get('score', 0)}%\n"
        f"- 可用于岗位匹配：{'是' if profile.completion.get('match_ready') else '否'}\n"
        f"- 职业阶段：{profile.career.get('career_stage') or '待补充'}\n"
        f"- 目标岗位：{roles}\n"
        f"- 首选城市：{locations}\n"
        f"- 技能标签：{skills}\n"
        f"- 缺少的必要信息：{missing_text}\n"
    )


def _safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", value).strip(" .")
    return re.sub(r"\s+", "-", value)[:80] or "candidate"


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
