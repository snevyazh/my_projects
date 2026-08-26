from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class DjVuDependencyError(RuntimeError):
    pass


class DjVuConversionError(RuntimeError):
    pass


def check_djvu_dependencies() -> None:
    missing = [name for name in ("ddjvu", "djvused") if shutil.which(name) is None]
    if missing:
        raise DjVuDependencyError(
            f"Missing DjVu conversion dependencies: {', '.join(missing)}. "
            "On Debian/Ubuntu run: sudo apt install djvulibre-bin"
        )


def djvu_page_count(input_path: Path) -> int:
    check_djvu_dependencies()
    completed = subprocess.run(
        ["djvused", "-e", "n", str(input_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        count = int(completed.stdout.strip())
    except ValueError:
        count = 0
    if completed.returncode or count < 1:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DjVuConversionError(f"Could not read DjVu page count for {input_path}: {detail}")
    return count


def djvu_page_to_pdf(input_path: Path, page_number: int, output_path: Path) -> Path:
    """Render one DjVu page to a disposable PDF."""
    check_djvu_dependencies()
    command = [
        "ddjvu",
        "-subsample=2",
        f"-page={page_number}",
        "-format=pdf",
        str(input_path),
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DjVuConversionError(
            f"ddjvu failed while rendering page {page_number} of {input_path}: {detail}"
        )
    if not output_path.is_file() or not output_path.stat().st_size:
        raise DjVuConversionError(
            f"DjVu page {page_number} produced no readable PDF: {input_path}"
        )
    return output_path


def djvu_to_pdf(input_path: Path, work_dir: Path) -> Path:
    """Render a DjVu document to a temporary PDF for the structured OCR pipeline."""
    check_djvu_dependencies()
    pdf_path = work_dir / "djvu-source.pdf"
    command = [
        "ddjvu",
        "-subsample=2",
        "-format=pdf",
        str(input_path),
        str(pdf_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DjVuConversionError(
            f"ddjvu failed while converting {input_path}: {detail}"
        )
    if not pdf_path.is_file() or not pdf_path.stat().st_size:
        raise DjVuConversionError(f"DjVu conversion produced no readable PDF: {input_path}")
    return pdf_path
