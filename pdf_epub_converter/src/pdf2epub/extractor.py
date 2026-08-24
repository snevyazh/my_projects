from __future__ import annotations

from pathlib import Path

from .analyzer import PageAnalysis
from .config import ConversionConfig
from .images import extract_page_images
from .models import BoundingBox, Page, TextBlock


class ExtractionError(RuntimeError):
    pass


def _text_block(raw: dict, page_number: int, page_width: float, source: str) -> TextBlock | None:
    lines: list[str] = []
    spans: list[dict] = []
    for line in raw.get("lines", []):
        line_spans = line.get("spans", [])
        text = "".join(span.get("text", "") for span in line_spans).strip()
        if text:
            lines.append(text)
            spans.extend(line_spans)
    text = "\n".join(lines).strip()
    if not text:
        return None
    sizes = [float(span.get("size", 0.0)) for span in spans if span.get("size")]
    font_size = sum(sizes) / len(sizes) if sizes else None
    names = [str(span.get("font", "")) for span in spans if span.get("font")]
    font_name = max(set(names), key=names.count) if names else None
    bbox = BoundingBox(*map(float, raw["bbox"]))
    flags = [int(span.get("flags", 0)) for span in spans]
    bold = any("bold" in str(span.get("font", "")).lower() or flag & 16 for span, flag in zip(spans, flags))
    centered = abs(((bbox.x0 + bbox.x1) / 2) - (page_width / 2)) <= page_width * 0.08
    return TextBlock(
        text=text,
        bbox=bbox,
        font_size=font_size,
        font_name=font_name,
        page_number=page_number,
        source="ocr" if source == "ocr" else "native",
        bold=bold,
        centered=centered,
    )


def extract_document(
    pdf_path: Path,
    analyses: list[PageAnalysis],
    ocr_pages: frozenset[int],
    work_dir: Path,
    config: ConversionConfig,
) -> list[Page]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("PyMuPDF is required for extraction") from exc
    analysis_by_page = {item.page_number: item for item in analyses}
    pages: list[Page] = []
    seen_images: dict[str, Path] = {}
    try:
        document = fitz.open(pdf_path)
        try:
            for index, pdf_page in enumerate(document):
                number = index + 1
                analysis = analysis_by_page[number]
                page = Page(number, pdf_page.rect.width, pdf_page.rect.height, analysis.kind)
                raw = pdf_page.get_text("dict", sort=False)
                for block in raw.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    parsed = _text_block(
                        block,
                        number,
                        page.width,
                        "ocr" if number in ocr_pages else "native",
                    )
                    if parsed:
                        page.blocks.append(parsed)
                page.blocks.extend(
                    extract_page_images(
                        document,
                        pdf_page,
                        number,
                        analysis.kind,
                        work_dir / "images",
                        config,
                        seen_images,
                    )
                )
                if not page.blocks:
                    page.warnings.append(f"Page {number} has no extracted content")
                pages.append(page)
        finally:
            document.close()
    except Exception as exc:
        raise ExtractionError(f"Failed to extract {pdf_path}: {exc}") from exc
    return pages
