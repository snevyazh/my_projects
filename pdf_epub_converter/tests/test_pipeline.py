from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("ebooklib")

from pdf2epub.pipeline import convert_pdf


def make_tiny_pdf(path: Path, *, include_picture: bool = False) -> None:
    document = fitz.open()
    picture = None
    if include_picture:
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
        pixmap.clear_with(180)
        picture = pixmap.tobytes("png")
    for number in (1, 2):
        page = document.new_page(width=600, height=800)
        page.insert_text((220, 90), f"Chapter {number}", fontsize=20)
        paragraph = (
            f"This is native selectable text for chapter {number}. "
            "It is deliberately long enough to pass native page classification. "
            "The converter should preserve this text and must not invoke OCR for this page. "
        )
        page.insert_textbox(fitz.Rect(60, 150, 540, 350), paragraph * 2, fontsize=11)
        if picture is not None:
            page.insert_image(fitz.Rect(200, 400, 400, 600), stream=picture)
        page.insert_text((290, 770), str(number), fontsize=9)
    document.set_metadata({"title": "Tiny Book", "author": "Test Author"})
    document.save(path)
    document.close()


def test_native_pdf_to_valid_epub(tmp_path: Path) -> None:
    source = tmp_path / "tiny.pdf"
    target = tmp_path / "tiny.epub"
    make_tiny_pdf(source)
    result = convert_pdf(source, target, cover=False)
    assert result.pages == 2
    assert result.ocr_pages == 0
    assert result.chapters == 2
    with zipfile.ZipFile(target) as archive:
        assert archive.read("mimetype") == b"application/epub+zip"
        names = archive.namelist()
        assert any(name.endswith("nav.xhtml") for name in names)
        chapter_names = [name for name in names if "chapter_" in name]
        assert len(chapter_names) == 2
        combined = b"".join(archive.read(name) for name in chapter_names)
        assert b"native selectable text" in combined


def test_can_omit_source_pictures(tmp_path: Path) -> None:
    source = tmp_path / "illustrated.pdf"
    with_pictures = tmp_path / "with-pictures.epub"
    without_pictures = tmp_path / "without-pictures.epub"
    make_tiny_pdf(source, include_picture=True)

    included = convert_pdf(source, with_pictures, cover=False)
    omitted = convert_pdf(source, without_pictures, cover=False, save_images=False)

    assert included.images == 2
    assert omitted.images == 0
    with zipfile.ZipFile(without_pictures) as archive:
        assert not any(name.startswith("EPUB/images/") for name in archive.namelist())
