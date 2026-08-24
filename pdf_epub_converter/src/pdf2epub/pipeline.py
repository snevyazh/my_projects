from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .analyzer import analyze_pdf
from .chapters import detect_chapters
from .cleaner import clean_document
from .config import ConversionConfig
from .epub import build_epub
from .extractor import extract_document
from .images import extract_dominant_first_page_image, render_cover
from .layout import associate_image_captions, reconstruct_layout
from .metadata import extract_metadata
from .models import Book, ImageBlock
from .ocr import ocr_pdf


@dataclass(frozen=True, slots=True)
class ConversionResult:
    input_path: Path
    output_path: Path
    pages: int
    native_pages: int
    ocr_pages: int
    images: int
    chapters: int
    warnings: tuple[str, ...]
    temp_path: Path | None = None


def convert_pdf(
    input_path: Path,
    output_path: Path,
    *,
    languages: str = "rus+eng+heb",
    title: str | None = None,
    author: str | None = None,
    cover: bool = True,
    keep_temp: bool = False,
    force: bool = False,
    config: ConversionConfig | None = None,
    logger: logging.Logger | None = None,
) -> ConversionResult:
    config = config or ConversionConfig()
    logger = logger or logging.getLogger("pdf2epub")
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not input_path.is_file() or input_path.suffix.casefold() != ".pdf":
        raise ValueError(f"Input is not a PDF file: {input_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"Output already exists (use --force): {output_path}")

    work_dir = Path(tempfile.mkdtemp(prefix="pdf2epub-"))
    succeeded = False
    try:
        logger.debug("Analyzing %s", input_path)
        analyses = analyze_pdf(input_path, config)
        ocr_result = ocr_pdf(input_path, analyses, work_dir, languages)
        pages = extract_document(
            ocr_result.pdf_path, analyses, ocr_result.page_numbers, work_dir, config
        )
        reconstruct_layout(pages)
        clean_document(pages, config)
        for page in pages:
            associate_image_captions(page)
        metadata = extract_metadata(input_path, title, author)
        book = Book(metadata=metadata, pages=pages)
        book.chapters = detect_chapters(pages, config)
        if not book.chapters:
            raise ValueError(f"No content could be extracted from {input_path}")
        if cover:
            try:
                book.cover_path = extract_dominant_first_page_image(input_path, work_dir)
                if book.cover_path is None:
                    book.cover_path = render_cover(
                        input_path, work_dir / "cover.jpg", config.cover_dpi
                    )
            except Exception as exc:
                book.warnings.append(f"Cover generation failed: {exc}")
        warnings = [warning for page in pages for warning in page.warnings]
        warnings.extend(book.warnings)
        image_count = sum(
            1 for page in pages for block in page.blocks if isinstance(block, ImageBlock)
        )
        if image_count > config.suspicious_image_count:
            warnings.append(f"Suspiciously large image count: {image_count}")
        if len(book.chapters) == 1 and book.chapters[0].title == "Book":
            warnings.append("No reliable chapter boundaries were detected")
        for warning in warnings:
            logger.warning(warning)
        build_epub(book, output_path)
        succeeded = True
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            pages=len(pages),
            native_pages=sum(item.native_character_count >= 30 for item in analyses),
            ocr_pages=len(ocr_result.page_numbers),
            images=image_count,
            chapters=len(book.chapters),
            warnings=tuple(warnings),
            temp_path=work_dir if keep_temp else None,
        )
    finally:
        if not keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)
        elif not succeeded:
            logger.info("Temporary files retained at %s", work_dir)
