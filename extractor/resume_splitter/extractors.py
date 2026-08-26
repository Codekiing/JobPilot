from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".tex", ".latex", ".md", ".markdown", ".txt"}


class ExtractionError(RuntimeError):
    """Raised when a resume cannot be converted to usable text."""


@dataclass(slots=True)
class ExtractedText:
    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def extract_text(path: Path) -> ExtractedText:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(f"不支持的文件格式: {suffix or '<无扩展名>'}")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in {".doc", ".odt"}:
        return _extract_legacy_word(path)
    if suffix in {".tex", ".latex"}:
        return _extract_latex(path)
    return _extract_plain_text(path, markdown=suffix in {".md", ".markdown"})


def _extract_pdf(path: Path) -> ExtractedText:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionError("解析 PDF 需要安装 pdfplumber") from exc

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages.append(_reflow_pdf_text(text.strip()))

    combined = "\n\n".join(text for text in pages if text)
    warnings: list[str] = []
    if not combined.strip():
        raise ExtractionError("PDF 中没有可提取文本；扫描件请先执行 OCR 后再解析")
    if len(combined.strip()) < 80:
        warnings.append("PDF 提取出的文本很少，文件可能是扫描件或包含复杂排版")
    return ExtractedText(
        text=combined,
        metadata={"extractor": "pdfplumber", "page_count": len(pages)},
        warnings=warnings,
    )


_PDF_DATE_START = re.compile(r"^(?:19|20)\d{2}(?:[./年-]\d{1,2})?")
_PDF_NEW_RECORD = re.compile(
    r"^(?:[-*+]\s+|GPA\s*[：:]|邮箱\s*[：:]|电话\s*[：:]|求职意向\s*[：:]|"
    r"[A-Z][A-Z0-9.-]{1,15}\s+(?:19|20)\d{2}\b|"
    r"教育背景$|教育经历$|工作经历$|实习经历$|项目经历$|科研经历$|开源贡献$|"
    r"论文经历$|核心技能$|专业技能$|荣誉奖项$|自我评价$)",
    re.IGNORECASE,
)


def _reflow_pdf_text(text: str) -> str:
    """Join visual hard-wraps while retaining headings and resume records."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    result = [lines[0]]
    for line in lines[1:]:
        previous = result[-1]
        should_join = (
            len(previous) >= 36
            and not re.search(r"[。.!?！？；;：:]$", previous)
            and not _PDF_DATE_START.match(previous)
            and not _PDF_DATE_START.match(line)
            and not _PDF_NEW_RECORD.match(line)
        )
        if should_join:
            separator = ""
            if re.search(r"[A-Za-z0-9)]$", previous) and re.match(r"[A-Za-z0-9(]", line):
                separator = " "
            result[-1] = previous + separator + line
        else:
            result.append(line)
    return "\n".join(result)


def _iter_docx_blocks(document):
    from docx.document import Document as DocumentObject
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if not isinstance(document, DocumentObject):
        return
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _extract_docx(path: Path) -> ExtractedText:
    try:
        from docx import Document
        from docx.table import Table
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionError("解析 DOCX 需要安装 python-docx") from exc

    document = Document(str(path))
    lines: list[str] = []
    for block in _iter_docx_blocks(document):
        if isinstance(block, Table):
            for row in block.rows:
                cells = [" ".join(cell.text.split()) for cell in row.cells]
                cells = list(dict.fromkeys(cell for cell in cells if cell))
                if cells:
                    lines.append(" | ".join(cells))
            continue
        text = " ".join(block.text.split())
        if not text:
            continue
        style_name = (block.style.name if block.style else "") or ""
        if style_name.lower().startswith("heading") or style_name.startswith("标题"):
            lines.append(f"## {text}")
        else:
            lines.append(text)
    return ExtractedText(
        text="\n".join(lines),
        metadata={"extractor": "python-docx", "paragraph_or_table_line_count": len(lines)},
    )


def _extract_legacy_word(path: Path) -> ExtractedText:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ExtractionError("解析 DOC/ODT 需要 LibreOffice（soffice）")
    with tempfile.TemporaryDirectory(prefix="resume-word-") as tmp:
        output_dir = Path(tmp)
        process = subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", str(output_dir), str(path)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        converted = output_dir / f"{path.stem}.docx"
        if process.returncode != 0 or not converted.exists():
            detail = (process.stderr or process.stdout).strip()
            raise ExtractionError(f"LibreOffice 转换失败: {detail or '未生成 DOCX'}")
        result = _extract_docx(converted)
        result.metadata["converted_from"] = path.suffix.lower()
        return result


def _extract_plain_text(path: Path, *, markdown: bool) -> ExtractedText:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            return ExtractedText(
                text=text,
                metadata={"extractor": "markdown" if markdown else "plain-text", "encoding": encoding},
            )
        except UnicodeDecodeError:
            continue
    raise ExtractionError("无法识别文本文件编码")


def _extract_latex(path: Path) -> ExtractedText:
    source = _extract_plain_text(path, markdown=False).text
    # Remove unescaped comments and document-only declarations.
    source = re.sub(r"(?<!\\)%.*$", "", source, flags=re.MULTILINE)
    source = re.sub(r"\\(?:documentclass|usepackage)(?:\[[^]]*])?\{[^{}]*}", "", source)
    source = re.sub(r"\\begin\{(?:document|itemize|enumerate|tabular\*?|center|flushleft|flushright)}(?:\{[^{}]*})?", "\n", source)
    source = re.sub(r"\\end\{[^{}]+}", "\n", source)

    # Preserve semantic section boundaries before removing generic commands.
    source = re.sub(
        r"\\(?:section|subsection|cvsection|cvsubsection)\*?\{([^{}]+)}",
        lambda m: f"\n## {m.group(1)}\n",
        source,
    )
    source = re.sub(r"\\item\s*", "\n- ", source)
    source = re.sub(
        r"\\href\{([^{}]+)}\{([^{}]+)}",
        lambda m: f"{m.group(2)} ({m.group(1)})",
        source,
    )
    source = re.sub(r"\\(?:email|phone|homepage|linkedin|github)\{([^{}]+)}", r"\1", source)
    source = source.replace("\\\\", "\n")
    source = source.replace("--", "-")

    # Repeatedly unwrap simple formatting commands while keeping their text.
    simple_command = re.compile(r"\\[A-Za-z@]+\*?(?:\[[^]]*])?\{([^{}]*)}")
    previous = None
    while previous != source:
        previous = source
        source = simple_command.sub(r"\1", source)

    source = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^]]*])?", " ", source)
    source = re.sub(r"[{}]", " ", source)
    replacements = {
        r"\&": "&",
        r"\%": "%",
        r"\_": "_",
        "~": " ",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in source.splitlines()]
    text = "\n".join(line for line in lines if line)
    return ExtractedText(text=text, metadata={"extractor": "latex-source"})
