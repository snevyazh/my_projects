from pdf2epub.cleaner import (
    clean_document,
    find_repeated_margin_text,
    join_wrapped_lines,
    repair_hyphenation,
)
from pdf2epub.config import ConversionConfig
from pdf2epub.models import BoundingBox, Page, PageKind, TextBlock


def block(text: str, page: int, y0: float, y1: float) -> TextBlock:
    return TextBlock(text, BoundingBox(50, y0, 550, y1), 11, "Serif", page)


def test_repairs_latin_and_cyrillic_wrap_hyphenation() -> None:
    assert repair_hyphenation("inter-\nnational") == "international"
    assert repair_hyphenation("между-\nнародный") == "международный"
    assert repair_hyphenation("well-\nknown") == "well-known"


def test_joins_wrapped_lines_but_preserves_paragraph_break() -> None:
    text = "This is the first line\nof one paragraph.\n\nSecond paragraph."
    assert join_wrapped_lines(text) == "This is the first line of one paragraph.\n\nSecond paragraph."


def test_removes_repeated_headers_and_page_numbers() -> None:
    pages = []
    for number in range(1, 6):
        pages.append(
            Page(
                number,
                600,
                800,
                PageKind.NATIVE,
                [
                    block("A Book Title", number, 20, 35),
                    block(f"Body paragraph {number}.", number, 150, 180),
                    block(str(number), number, 770, 785),
                ],
            )
        )
    assert "a book title" in find_repeated_margin_text(pages, ConversionConfig())
    clean_document(pages, ConversionConfig())
    assert [[item.text for item in page.blocks] for page in pages] == [
        [f"Body paragraph {number}."] for number in range(1, 6)
    ]


def test_alternating_headers_are_removed_when_each_repeats_enough() -> None:
    config = ConversionConfig(repeated_header_threshold=0.4, repeated_header_min_pages=2)
    pages = [
        Page(
            number,
            600,
            800,
            PageKind.NATIVE,
            [block("Author" if number % 2 else "Book", number, 20, 35), block("Body.", number, 120, 140)],
        )
        for number in range(1, 7)
    ]
    clean_document(pages, config)
    assert all([item.text for item in page.blocks] == ["Body."] for page in pages)

