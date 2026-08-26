from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def output_path(output_root: Path, profile_id: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_root / profile_id / stamp / "job-filter.html"


def update_manifest(output_root: Path, html_path: Path, data: dict[str, Any]) -> None:
    manifest = {
        "latest": str(html_path.resolve()),
        "profile_id": data["profile_id"],
        "source_matcher_json": data["source_matcher_json"],
        "source_matcher_sha256": data["source_matcher_sha256"],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
