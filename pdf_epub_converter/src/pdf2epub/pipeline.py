from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .analyzer import analyze_pdf
from .chapters import detect_chapters
from .cleaner import clean_document
from .config import ConversionConfig
from .djvu import djvu_page_count, djvu_page_to_pdf
from .epub import build_epub
from .extractor import extract_document
from .images import extract_dominant_first_page_image, render_cover
from .layout import associate_image_captions, reconstruct_layout
from .metadata import extract_metadata, title_from_filename
from .models import Book, BookMetadata, ImageBlock, Page
from .ocr import ocr_pdf

SUPPORTED_INPUT_SUFFIXES = frozenset({".pdf", ".djvu", ".djv"})
ProgressCallback = Callable[[int, int], None]


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
    save_images: bool = True,
    keep_temp: bool = False,
    force: bool = False,
    config: ConversionConfig | None = None,
    logger: logging.Logger | None = None,
    progress_callback: ProgressCallback | None = None,
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
            ocr_result.pdf_path,
            analyses,
            ocr_result.page_numbers,
            work_dir,
            config,
            save_images=save_images,
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
        warnings.extend(ocr_result.warnings)
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
            native_pages=sum(
                item.native_character_count >= 30 and item.native_text_reliable
                for item in analyses
            ),
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


def convert_djvu(
    input_path: Path,
    output_path: Path,
    *,
    languages: str = "rus+eng+heb",
    title: str | None = None,
    author: str | None = None,
    cover: bool = True,
    save_images: bool = True,
    keep_temp: bool = False,
    force: bool = False,
    config: ConversionConfig | None = None,
    logger: logging.Logger | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ConversionResult:
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file() or input_path.suffix.casefold() not in {".djvu", ".djv"}:
        raise ValueError(f"Input is not a DjVu file: {input_path}")
    output_path = output_path.expanduser().resolve()
    if output_path.exists() and not force:
        raise FileExistsError(f"Output already exists (use --force): {output_path}")
    work_dir = Path(tempfile.mkdtemp(prefix="pdf2epub-djvu-"))
    logger = logger or logging.getLogger("pdf2epub")
    config = config or ConversionConfig()
    try:
        total_pages = djvu_page_count(input_path)
        logger.info("Processing %d DjVu pages one at a time", total_pages)
        pages: list[Page] = []
        warnings: list[str] = []
        seen_images: dict[str, Path] = {}
        metadata: BookMetadata | None = None
        cover_path: Path | None = None
        ocr_page_count = 0
        page_work = work_dir / "page"
        image_dir = work_dir / "images"

        for page_number in range(1, total_pages + 1):
            if page_number == 1 or page_number == total_pages or page_number % 10 == 0:
                logger.info("Processing DjVu page %d/%d", page_number, total_pages)
            page_work.mkdir(parents=True, exist_ok=True)
            try:
                page_pdf = djvu_page_to_pdf(
                    input_path, page_number, page_work / "source.pdf"
                )
                analyses = analyze_pdf(page_pdf, config)
                ocr_result = ocr_pdf(page_pdf, analyses, page_work, languages)
                extracted = extract_document(
                    ocr_result.pdf_path,
                    analyses,
                    ocr_result.page_numbers,
                    page_work,
                    config,
                    save_images=save_images,
                    page_number_offset=page_number - 1,
                    image_dir=image_dir,
                    seen_images=seen_images,
                )
                pages.extend(extracted)
                ocr_page_count += len(ocr_result.page_numbers)
                warnings.extend(ocr_result.warnings)
                if page_number == 1:
                    metadata = extract_metadata(
                        page_pdf,
                        title or title_from_filename(input_path),
                        author,
                    )
                    if cover:
                        try:
                            cover_path = extract_dominant_first_page_image(page_pdf, work_dir)
                            if cover_path is None:
                                cover_path = render_cover(
                                    page_pdf, work_dir / "cover.jpg", config.cover_dpi
                                )
                        except Exception as exc:
                            warnings.append(f"Cover generation failed: {exc}")
            finally:
                shutil.rmtree(page_work, ignore_errors=True)
            if progress_callback is not None:
                progress_callback(page_number, total_pages)

        reconstruct_layout(pages)
        clean_document(pages, config)
        for page in pages:
            associate_image_captions(page)
        if metadata is None:
            raise ValueError(f"No pages could be extracted from {input_path}")
        book = Book(metadata=metadata, pages=pages, cover_path=cover_path)
        book.chapters = detect_chapters(pages, config)
        if not book.chapters:
            raise ValueError(f"No content could be extracted from {input_path}")
        warnings.extend(warning for page in pages for warning in page.warnings)
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
        return ConversionResult(
            input_path=input_path,
            output_path=output_path,
            pages=len(pages),
            native_pages=0,
            ocr_pages=ocr_page_count,
            images=image_count,
            chapters=len(book.chapters),
            warnings=tuple(warnings),
            temp_path=work_dir if keep_temp else None,
        )
    finally:
        if not keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            logger.info("DjVu temporary files retained at %s", work_dir)


def convert_document(input_path: Path, output_path: Path, **options: object) -> ConversionResult:
    suffix = input_path.expanduser().suffix.casefold()
    if suffix == ".pdf":
        return convert_pdf(input_path, output_path, **options)
    if suffix in {".djvu", ".djv"}:
        return convert_djvu(input_path, output_path, **options)
    supported = ", ".join(sorted(SUPPORTED_INPUT_SUFFIXES))
    raise ValueError(f"Unsupported input format {suffix or '(none)'}; expected one of: {supported}")
