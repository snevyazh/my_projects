from __future__ import annotations

import hashlib
from pathlib import Path

from .config import ConversionConfig
from .models import BoundingBox, ImageBlock, PageKind


def _extension_and_media(ext: str) -> tuple[str, str]:
    normalized = ext.lower().lstrip(".")
    if normalized in {"jpg", "jpeg"}:
        return "jpg", "image/jpeg"
    if normalized == "png":
        return "png", "image/png"
    return "png", "image/png"


def _write_pdf_image(payload: dict, destination: Path) -> None:
    source_ext = str(payload.get("ext", "")).lower().lstrip(".")
    data = payload.get("image", b"")
    if source_ext in {"jpg", "jpeg", "png"}:
        destination.write_bytes(data)
        return
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as source:
        source.convert("RGB").save(destination, "PNG")


def extract_page_images(
    document: object,
    page: object,
    page_number: int,
    page_kind: PageKind,
    image_dir: Path,
    config: ConversionConfig,
    seen: dict[str, Path],
) -> list[ImageBlock]:
    """Extract meaningful embedded images while rejecting scan backgrounds and noise."""
    image_dir.mkdir(parents=True, exist_ok=True)
    page_area = float(page.rect.width * page.rect.height)
    result: list[ImageBlock] = []
    for image in page.get_images(full=True):
        xref = image[0]
        try:
            payload = document.extract_image(xref)
            rectangles = page.get_image_rects(xref)
        except Exception:
            continue
        width, height = int(payload.get("width", 0)), int(payload.get("height", 0))
        if width < config.min_image_width or height < config.min_image_height:
            continue
        data = payload.get("image", b"")
        digest = hashlib.sha256(data).hexdigest()
        for rectangle in rectangles:
            bbox = BoundingBox(rectangle.x0, rectangle.y0, rectangle.x1, rectangle.y1)
            ratio = bbox.area / page_area if page_area else 0.0
            if ratio < config.minimum_image_area_ratio:
                continue
            if page_kind == PageKind.SCANNED and ratio >= config.maximum_scan_image_area_ratio:
                continue
            extension, media_type = _extension_and_media(str(payload.get("ext", "png")))
            file_path = seen.get(digest, image_dir / f"image_p{page_number:04d}_{xref}.{extension}")
            # Reuse one EPUB resource while retaining every meaningful placement.
            if digest not in seen:
                _write_pdf_image(payload, file_path)
                seen[digest] = file_path
            result.append(
                ImageBlock(
                    bbox=bbox,
                    page_number=page_number,
                    image_path=file_path,
                    width=width,
                    height=height,
                    media_type=media_type,
                )
            )
    return result


def render_cover(pdf_path: Path, output_path: Path, dpi: int = 150) -> Path:
    import fitz

    with fitz.open(pdf_path) as document:
        if not document.page_count:
            raise ValueError("Cannot create a cover from an empty PDF")
        pixmap = document[0].get_pixmap(dpi=dpi, alpha=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(output_path)
    return output_path


def extract_dominant_first_page_image(
    pdf_path: Path, output_dir: Path, minimum_coverage: float = 0.45
) -> Path | None:
    """Use an existing dominant first-page raster as the cover when one is available."""
    import fitz

    with fitz.open(pdf_path) as document:
        if not document.page_count:
            return None
        page = document[0]
        page_area = page.rect.width * page.rect.height
        candidates: list[tuple[float, int]] = []
        for image in page.get_images(full=True):
            try:
                coverage = max(
                    (rect.width * rect.height / page_area for rect in page.get_image_rects(image[0])),
                    default=0.0,
                )
            except Exception:
                continue
            candidates.append((coverage, image[0]))
        if not candidates:
            return None
        coverage, xref = max(candidates)
        if coverage < minimum_coverage:
            return None
        payload = document.extract_image(xref)
        extension, _ = _extension_and_media(str(payload.get("ext", "png")))
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"cover.{extension}"
        _write_pdf_image(payload, destination)
        return destination
