from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("ebooklib")

from pdf2epub.pipeline import convert_pdf


def make_tiny_pdf(path: Path) -> None:
    document = fitz.open()
    for number in (1, 2):
        page = document.new_page(width=600, height=800)
        page.insert_text((220, 90), f"Chapter {number}", fontsize=20)
        paragraph = (
            f"This is native selectable text for chapter {number}. "
            "It is deliberately long enough to pass native page classification. "
            "The converter should preserve this text and must not invoke OCR for this page. "
        )
        page.insert_textbox(fitz.Rect(60, 150, 540, 350), paragraph * 2, fontsize=11)
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
