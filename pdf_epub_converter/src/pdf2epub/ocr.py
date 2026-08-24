from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .analyzer import PageAnalysis
from .models import PageKind


class OCRDependencyError(RuntimeError):
    pass


class OCRProcessingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OCRResult:
    pdf_path: Path
    page_numbers: frozenset[int]
    performed: bool


def pages_requiring_ocr(analyses: list[PageAnalysis]) -> list[int]:
    return [
        item.page_number
        for item in analyses
        if item.kind == PageKind.SCANNED
        or (item.kind == PageKind.MIXED and item.native_character_count < 30)
    ]


def compress_page_ranges(pages: list[int]) -> str:
    if not pages:
        return ""
    result: list[str] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        result.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    result.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(result)


def check_ocr_dependencies(languages: str) -> None:
    missing = [name for name in ("ocrmypdf", "tesseract") if shutil.which(name) is None]
    if missing:
        raise OCRDependencyError(
            f"Missing OCR dependencies: {', '.join(missing)}. On Debian/Ubuntu run: "
            "sudo apt install ocrmypdf tesseract-ocr tesseract-ocr-rus "
            "tesseract-ocr-eng tesseract-ocr-heb"
        )
    completed = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=False
    )
    installed = set(completed.stdout.splitlines()[1:])
    wanted = set(languages.split("+"))
    absent = sorted(wanted - installed)
    if absent:
        raise OCRDependencyError(
            f"Tesseract language data not installed: {', '.join(absent)}. "
            "Install the corresponding tesseract-ocr-<lang> packages."
        )


def ocr_pdf(
    input_path: Path,
    analyses: list[PageAnalysis],
    work_dir: Path,
    languages: str,
) -> OCRResult:
    pages = pages_requiring_ocr(analyses)
    if not pages:
        return OCRResult(input_path, frozenset(), False)
    check_ocr_dependencies(languages)
    output_path = work_dir / "ocr.pdf"
    command = [
        "ocrmypdf",
        "--skip-text",
        "--deskew",
        "--rotate-pages",
        "--pages",
        compress_page_ranges(pages),
        "-l",
        languages,
        str(input_path),
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown OCRmyPDF error"
        raise OCRProcessingError(f"OCRmyPDF failed for {input_path}: {detail}")
    return OCRResult(output_path, frozenset(pages), True)
