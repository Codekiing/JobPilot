from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import FillPlan


def save_plan(plan: FillPlan, output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_root.resolve() / plan.profile_id / stamp
    drafts_dir = run_dir / "application-drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    payload = plan.to_dict()
    _private_json(run_dir / "fill-plan.json", payload)
    for application in payload["applications"]:
        _private_json(drafts_dir / f"{application['draft_id']}.json", application)
    manifest = {
        "latest": str(run_dir.resolve()),
        "profile_id": plan.profile_id,
        "plan_id": plan.plan_id,
        "created_at": plan.created_at,
        "source_profile_json": plan.source_profile_json,
        "source_selected_jobs_json": plan.source_selected_jobs_json,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _private_json(output_root / "manifest.json", manifest)
    return run_dir


def save_fill_report(run_dir: Path, report: dict[str, Any]) -> Path:
    reports = run_dir / "fill-reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"{report['draft_id']}.json"
    _private_json(path, report)
    return path


def _private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
