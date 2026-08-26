from __future__ import annotations

import os
import re
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
    warnings: tuple[str, ...] = ()


def pages_requiring_ocr(analyses: list[PageAnalysis]) -> list[int]:
    return [
        item.page_number
        for item in analyses
        if not item.native_text_reliable
        or item.kind == PageKind.SCANNED
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


def _ocr_command(
    input_path: Path,
    output_path: Path,
    pages: list[int],
    languages: str,
    force_ocr: bool,
    jobs: int = 2,
) -> list[str]:
    return [
        "ocrmypdf",
        "--jobs",
        str(jobs),
        "--force-ocr" if force_ocr else "--skip-text",
        "--deskew",
        "--rotate-pages",
        "--oversample",
        "300",
        "--output-type",
        "pdf",
        "--optimize",
        "0",
        "--pages",
        compress_page_ranges(pages),
        "-l",
        languages,
        str(input_path),
        str(output_path),
    ]


def _stage_ocr_input(input_path: Path, work_dir: Path) -> Path:
    """Keep OCR input stable if the user moves or removes the selected file."""
    staged_input = work_dir / "ocr-input.pdf"
    try:
        os.link(input_path, staged_input)
    except OSError:
        try:
            shutil.copy2(input_path, staged_input)
        except OSError as exc:
            raise OCRProcessingError(f"Could not stage PDF for OCR: {input_path}: {exc}") from exc
    return staged_input


def _tesseract_failed_pages(detail: str) -> set[int]:
    return {
        int(match)
        for match in re.findall(
            r"\b(\d+)\s+\[tesseract\]\s+Error during processing\.", detail
        )
    }


def _failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    raw = completed.stderr.strip() or completed.stdout.strip() or "unknown OCRmyPDF error"
    status = (
        f"terminated by signal {-completed.returncode}"
        if completed.returncode < 0
        else f"exit code {completed.returncode}"
    )
    limit = 4000
    if len(raw) > limit:
        omitted = len(raw) - limit
        raw = f"[{omitted} earlier log characters omitted]\n{raw[-limit:]}"
    return f"{status}: {raw}"


def _repair_pdf_with_ghostscript(
    executable: str, input_path: Path, output_path: Path
) -> subprocess.CompletedProcess[str]:
    """Rebuild malformed PDF streams without downsampling page images."""
    return subprocess.run(
        [
            executable,
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dAutoRotatePages=/None",
            "-dDownsampleColorImages=false",
            "-dDownsampleGrayImages=false",
            "-dDownsampleMonoImages=false",
            f"-sOutputFile={output_path}",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        check=False,
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
    force_ocr = any(
        not item.native_text_reliable and item.native_character_count > 0
        for item in analyses
        if item.page_number in pages
    )
    staged_input = _stage_ocr_input(input_path, work_dir)
    output_path = work_dir / "ocr.pdf"
    command = _ocr_command(staged_input, output_path, pages, languages, force_ocr)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = _failure_detail(completed)
        if completed.returncode == 7:
            failed_details = [detail]
            output_path = work_dir / "ocr-single-job.pdf"
            command = _ocr_command(
                staged_input, output_path, pages, languages, force_ocr, jobs=1
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if not completed.returncode:
                return OCRResult(
                    output_path,
                    frozenset(pages),
                    True,
                    ("OCRmyPDF recovered after retrying with one worker.",),
                )
            detail = _failure_detail(completed)
            failed_details.append(detail)
            failed_pages = _tesseract_failed_pages("\n".join(failed_details))
            remaining_pages = [page for page in pages if page not in failed_pages]
            if failed_pages and remaining_pages:
                output_path = work_dir / "ocr-skipped-failed-pages.pdf"
                command = _ocr_command(
                    staged_input,
                    output_path,
                    remaining_pages,
                    languages,
                    force_ocr,
                    jobs=1,
                )
                completed = subprocess.run(
                    command, capture_output=True, text=True, check=False
                )
                if not completed.returncode:
                    skipped = compress_page_ranges(sorted(failed_pages))
                    return OCRResult(
                        output_path,
                        frozenset(remaining_pages),
                        True,
                        (
                            f"Tesseract could not process OCR pages {skipped}; "
                            "they were left unchanged.",
                        ),
                    )
                detail = _failure_detail(completed)
            elif failed_pages:
                skipped = compress_page_ranges(sorted(failed_pages))
                return OCRResult(
                    staged_input,
                    frozenset(),
                    False,
                    (
                        f"Tesseract could not process OCR pages {skipped}; "
                        "they were left unchanged.",
                    ),
                )
        if "generated pdf is invalid" not in detail.casefold():
            raise OCRProcessingError(f"OCRmyPDF failed for {input_path}: {detail}")

        ghostscript = shutil.which("gs") or shutil.which("gswin64c")
        if ghostscript is None:
            raise OCRProcessingError(
                f"OCRmyPDF failed for {input_path}: {detail}\n"
                "Automatic PDF repair is unavailable because Ghostscript (gs) is not installed."
            )

        repaired_input = work_dir / "repaired-input.pdf"
        repair = _repair_pdf_with_ghostscript(ghostscript, staged_input, repaired_input)
        if repair.returncode or not repaired_input.is_file():
            repair_detail = (
                repair.stderr.strip() or repair.stdout.strip() or "unknown Ghostscript error"
            )
            raise OCRProcessingError(
                f"OCRmyPDF failed for {input_path}: {detail}\n"
                f"Automatic PDF repair also failed: {repair_detail}"
            )

        output_path = work_dir / "ocr-repaired.pdf"
        command = _ocr_command(repaired_input, output_path, pages, languages, force_ocr)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            retry_detail = _failure_detail(completed)
            raise OCRProcessingError(
                f"OCRmyPDF failed for {input_path} after automatic PDF repair: {retry_detail}"
            )
        return OCRResult(
            output_path,
            frozenset(pages),
            True,
            ("The source PDF contained malformed streams and was repaired before OCR.",),
        )
    return OCRResult(output_path, frozenset(pages), True)
