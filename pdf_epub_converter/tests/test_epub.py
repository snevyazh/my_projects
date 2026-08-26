from __future__ import annotations

import zipfile
from pathlib import Path

from pdf2epub.epub import build_epub
from pdf2epub.models import Book, BookMetadata, BoundingBox, Chapter, TextBlock


def test_build_epub_sanitizes_xml_forbidden_characters(tmp_path: Path) -> None:
    block = TextBlock("one\x00two\x01three", BoundingBox(0, 0, 100, 20), 12, None, 1)
    book = Book(
        metadata=BookMetadata(title="A\x0e title", authors=["An\x02 Author"]),
        pages=[],
        chapters=[Chapter("A\x03 chapter", [block], 1)],
    )
    output = tmp_path / "book.epub"

    build_epub(book, output)

    with zipfile.ZipFile(output) as archive:
        xml = b"".join(
            archive.read(name)
            for name in archive.namelist()
            if name.endswith((".xhtml", ".opf", ".ncx"))
        )
    assert b"one two three" in xml
    assert all(byte not in xml for byte in (0, 1, 2, 3, 14))
