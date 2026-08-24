from __future__ import annotations

import re
import uuid
from pathlib import Path

from .models import BookMetadata


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\x00", "").split()).strip()


def title_from_filename(path: Path) -> str:
    title = re.sub(r"[_\.]+", " ", path.stem)
    title = re.sub(r"\s+", " ", title).strip()
    return title or "Untitled"


def extract_metadata(path: Path, title: str | None = None, author: str | None = None) -> BookMetadata:
    pdf_metadata: dict[str, object] = {}
    try:
        import fitz

        with fitz.open(path) as document:
            pdf_metadata = document.metadata or {}
    except Exception:
        pass
    resolved_title = _clean(title) or _clean(pdf_metadata.get("title")) or title_from_filename(path)
    resolved_author = _clean(author) or _clean(pdf_metadata.get("author"))
    language = _clean(pdf_metadata.get("language")) or "und"
    subject = _clean(pdf_metadata.get("subject")) or None
    keywords = [item.strip() for item in _clean(pdf_metadata.get("keywords")).split(",") if item.strip()]
    return BookMetadata(
        title=resolved_title,
        authors=[resolved_author] if resolved_author else [],
        language=language,
        subject=subject,
        keywords=keywords,
        identifier=f"urn:uuid:{uuid.uuid4()}",
    )
