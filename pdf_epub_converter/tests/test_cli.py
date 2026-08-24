from pathlib import Path

from pdf2epub.cli import discover_documents, output_for


def test_discovers_pdf_and_djvu_case_insensitively(tmp_path: Path) -> None:
    for name in ("one.pdf", "two.DJVU", "three.djv", "ignore.txt"):
        (tmp_path / name).touch()
    assert [path.name for path in discover_documents(tmp_path, False)] == [
        "one.pdf",
        "three.djv",
        "two.DJVU",
    ]


def test_djvu_output_uses_epub_suffix() -> None:
    source = Path("/books/story.djvu")
    assert output_for(source, None, None) == Path("/books/story.epub")
