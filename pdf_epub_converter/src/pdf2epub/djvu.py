from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class DjVuDependencyError(RuntimeError):
    pass


class DjVuConversionError(RuntimeError):
    pass


def check_djvu_dependencies() -> None:
    missing = [name for name in ("ddjvu",) if shutil.which(name) is None]
    if missing:
        raise DjVuDependencyError(
            f"Missing DjVu conversion dependencies: {', '.join(missing)}. "
            "On Debian/Ubuntu run: sudo apt install djvulibre-bin"
        )


def djvu_to_pdf(input_path: Path, work_dir: Path) -> Path:
    """Render a DjVu document to a temporary PDF for the structured OCR pipeline."""
    check_djvu_dependencies()
    pdf_path = work_dir / "djvu-source.pdf"
    command = ["ddjvu", "-format=pdf", str(input_path), str(pdf_path)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DjVuConversionError(
            f"ddjvu failed while converting {input_path}: {detail}"
        )
    if not pdf_path.is_file() or not pdf_path.stat().st_size:
        raise DjVuConversionError(f"DjVu conversion produced no readable PDF: {input_path}")
    return pdf_path
