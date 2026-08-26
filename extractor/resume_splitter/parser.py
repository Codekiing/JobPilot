from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .extractors import SUPPORTED_EXTENSIONS, extract_text
from .models import ResumeDocument
from .sectioner import extract_profile, normalize_text, split_sections
from .storage import save_document, save_manifest


class ResumeParser:
    """Extract and persist locally structured resume sections."""

    def parse_file(self, path: str | Path) -> ResumeDocument:
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"简历文件不存在: {source_path}")

        extracted = extract_text(source_path)
        raw_text = normalize_text(extracted.text)
        stat = source_path.stat()
        digest = _sha256(source_path)
        document = ResumeDocument(
            schema_version="1.0",
            source={
                "file_name": source_path.name,
                "path": str(source_path),
                "format": source_path.suffix.lower().lstrip("."),
                "sha256": digest,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
            profile=extract_profile(raw_text),
            sections=split_sections(raw_text),
            raw_text=raw_text,
            warnings=extracted.warnings,
            extraction=extracted.metadata,
        )
        if len(document.sections) <= 1:
            document.warnings.append("未识别出明确栏目，请检查简历标题或扩展 SECTION_ALIASES")
        return document

    def parse_and_save(self, path: str | Path, output_root: str | Path = "outputs") -> tuple[ResumeDocument, Path]:
        document = self.parse_file(path)
        saved_to = save_document(document, Path(output_root).expanduser().resolve())
        return document, saved_to

    def parse_directory(
        self,
        input_dir: str | Path = "inputs",
        output_root: str | Path = "outputs",
        *,
        recursive: bool = False,
    ) -> list[dict[str, object]]:
        source_dir = Path(input_dir).expanduser().resolve()
        if not source_dir.is_dir():
            raise NotADirectoryError(f"输入目录不存在: {source_dir}")
        iterator = source_dir.rglob("*") if recursive else source_dir.glob("*")
        paths = sorted(
            (path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
            key=lambda path: str(path).casefold(),
        )
        records: list[dict[str, object]] = []
        for path in paths:
            try:
                document, saved_to = self.parse_and_save(path, output_root)
                records.append(
                    {
                        "source": str(path),
                        "status": "ok",
                        "output": str(saved_to),
                        "section_count": len(document.sections),
                        "warnings": document.warnings,
                    }
                )
            except Exception as exc:  # continue processing the remaining batch
                records.append({"source": str(path), "status": "error", "error": str(exc)})
        save_manifest(records, Path(output_root).expanduser().resolve())
        return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
