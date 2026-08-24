from pdf2epub.chapters import detect_chapters
from pdf2epub.config import ConversionConfig
from pdf2epub.models import BoundingBox, Page, PageKind, TextBlock


def text(value: str, page: int, y: float, size: float = 11, bold: bool = False, centered: bool = False) -> TextBlock:
    return TextBlock(value, BoundingBox(50, y, 550, y + 25), size, "Serif", page, bold=bold, centered=centered)


def test_detects_multilingual_explicit_chapters() -> None:
    pages = [
        Page(1, 600, 800, PageKind.NATIVE, [text("Глава 1", 1, 80), text("A" * 80, 1, 150)]),
        Page(2, 600, 800, PageKind.NATIVE, [text("פרק א", 2, 80), text("B" * 80, 2, 150)]),
    ]
    chapters = detect_chapters(pages, ConversionConfig())
    assert [chapter.title for chapter in chapters] == ["Глава 1", "פרק א"]


def test_detects_title_only_with_combined_visual_signals() -> None:
    pages = [
        Page(
            1,
            600,
            800,
            PageKind.NATIVE,
            [text("The Long Road", 1, 80, 18, True, True), text("Body " * 20, 1, 160)],
        )
    ]
    chapters = detect_chapters(pages, ConversionConfig())
    assert chapters[0].title == "The Long Road"


def test_prefers_single_book_when_uncertain() -> None:
    pages = [Page(1, 600, 800, PageKind.NATIVE, [text("ordinary paragraph " * 8, 1, 100)])]
    chapters = detect_chapters(pages, ConversionConfig())
    assert len(chapters) == 1
    assert chapters[0].title == "Book"

