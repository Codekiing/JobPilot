from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .models import ResumeDocument


def save_document(document: ResumeDocument, output_root: Path) -> Path:
    digest = str(document.source["sha256"])[:8]
    stem = _safe_name(Path(str(document.source["file_name"])).stem)
    document_dir = output_root / f"{stem}-{digest}"
    sections_dir = document_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    _atomic_write(
        document_dir / "resume.json",
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(document_dir / "raw.txt", document.raw_text.rstrip() + "\n")

    expected_files: set[str] = set()
    for section in document.sections:
        filename = f"{section.order:02d}-{_safe_name(section.title)}.md"
        expected_files.add(filename)
        body = f"# {section.title}\n\n{section.content.rstrip()}\n"
        _atomic_write(sections_dir / filename, body)

    # Remove only stale files previously managed by this component.
    for existing in sections_dir.glob("*.md"):
        if existing.name not in expected_files:
            existing.unlink()
    return document_dir


def save_manifest(records: list[dict[str, object]], output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "manifest.json"
    _atomic_write(path, json.dumps({"files": records}, ensure_ascii=False, indent=2) + "\n")
    return path


def _safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", value).strip(" .")
    value = re.sub(r"\s+", "-", value)
    return value[:100] or "resume"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
