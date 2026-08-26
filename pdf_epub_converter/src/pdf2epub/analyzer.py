from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ConversionConfig
from .models import BoundingBox, PageKind
from .text import has_invalid_xml_characters


class PDFAnalysisError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PageAnalysis:
    page_number: int
    width: float
    height: float
    native_character_count: int
    text_block_count: int
    image_count: int
    image_coverage: float
    text_coverage: float
    kind: PageKind
    native_text_reliable: bool = True


def _union_area(boxes: list[BoundingBox], page_area: float) -> float:
    # The sum is deliberately capped. Exact polygon union is unnecessary for classification.
    return min(1.0, sum(box.area for box in boxes) / page_area) if page_area else 0.0


def classify_page(
    native_characters: int,
    text_blocks: int,
    image_coverage: float,
    config: ConversionConfig,
    native_text_reliable: bool = True,
) -> PageKind:
    good_text = native_text_reliable and (
        native_characters >= config.min_native_chars
        or (native_characters >= 30 and text_blocks >= 2)
    )
    if good_text and image_coverage >= config.mixed_image_coverage:
        return PageKind.MIXED
    if good_text:
        return PageKind.NATIVE
    if image_coverage >= config.scanned_image_coverage:
        return PageKind.SCANNED
    if native_characters or text_blocks or image_coverage:
        return PageKind.MIXED
    return PageKind.EMPTY


def analyze_pdf(path: Path, config: ConversionConfig) -> list[PageAnalysis]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise PDFAnalysisError("PyMuPDF is required. Install the project dependencies.") from exc

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFAnalysisError(f"Cannot open PDF {path}: {exc}") from exc
    try:
        if document.needs_pass:
            raise PDFAnalysisError(f"PDF is encrypted or password-protected: {path}")
        analyses: list[PageAnalysis] = []
        for index, page in enumerate(document):
            width, height = page.rect.width, page.rect.height
            page_area = width * height
            raw = page.get_text("dict")
            text_boxes: list[BoundingBox] = []
            chars = 0
            text_blocks = 0
            native_text_reliable = True
            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue
                block_text = "".join(
                    span.get("text", "")
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                )
                if block_text.strip():
                    text_blocks += 1
                    chars += len(block_text.strip())
                    if has_invalid_xml_characters(block_text):
                        native_text_reliable = False
                    text_boxes.append(BoundingBox(*map(float, block["bbox"])))
            image_boxes: list[BoundingBox] = []
            for image in page.get_images(full=True):
                try:
                    image_boxes.extend(
                        BoundingBox(rect.x0, rect.y0, rect.x1, rect.y1)
                        for rect in page.get_image_rects(image[0])
                    )
                except Exception:
                    continue
            image_coverage = _union_area(image_boxes, page_area)
            kind = classify_page(
                chars,
                text_blocks,
                image_coverage,
                config,
                native_text_reliable,
            )
            analyses.append(
                PageAnalysis(
                    page_number=index + 1,
                    width=width,
                    height=height,
                    native_character_count=chars,
                    text_block_count=text_blocks,
                    image_count=len(image_boxes),
                    image_coverage=image_coverage,
                    text_coverage=_union_area(text_boxes, page_area),
                    kind=kind,
                    native_text_reliable=native_text_reliable,
                )
            )
        return analyses
    except PDFAnalysisError:
        raise
    except Exception as exc:
        raise PDFAnalysisError(f"Failed while analyzing {path}: {exc}") from exc
    finally:
        document.close()
