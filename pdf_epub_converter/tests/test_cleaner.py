from pathlib import Path

from pdf2epub.cleaner import (
    clean_document,
    find_repeated_margin_text,
    is_ocr_decoration_text,
    join_wrapped_lines,
    repair_hyphenation,
)
from pdf2epub.config import ConversionConfig
from pdf2epub.models import BoundingBox, ImageBlock, Page, PageKind, TextBlock


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


def test_removes_ornament_misread_as_mixed_script_heading() -> None:
    ornament = block("RES GUE EE 7 HECЯ ee HЯHЯ", 1, 35, 70)
    ornament.source = "ocr"
    body = block("СИСТЕМАМ И МИРОВОЗЗРЕНИЮ ЧЕЛОВЕКА ДРЕВНЕЙ РУСИ.", 1, 100, 130)
    body.source = "ocr"
    page = Page(1, 600, 800, PageKind.SCANNED, [ornament, body])

    clean_document([page], ConversionConfig())

    assert [item.text for item in page.blocks] == [body.text]


def test_removes_repeated_and_symbolic_ocr_ornaments() -> None:
    assert is_ocr_decoration_text("жхжхжхжх 7 жхжхжхжх")
    assert is_ocr_decoration_text("❦ — ❦ — ❦")


def test_removes_only_decorative_line_from_ocr_block() -> None:
    item = block("❦ — ❦ — ❦\nA real paragraph remains.", 1, 300, 350)
    item.source = "ocr"
    page = Page(1, 600, 800, PageKind.SCANNED, [item])

    clean_document([page], ConversionConfig())

    assert [entry.text for entry in page.blocks] == ["A real paragraph remains."]


def test_ornament_filter_is_ocr_only_and_can_be_disabled() -> None:
    native = block("RES GUE EE 7 HECЯ ee HЯHЯ", 1, 35, 70)
    ocr = block("❦ — ❦ — ❦", 2, 300, 320)
    ocr.source = "ocr"
    pages = [
        Page(1, 600, 800, PageKind.NATIVE, [native]),
        Page(2, 600, 800, PageKind.SCANNED, [ocr]),
    ]

    clean_document(pages, ConversionConfig(remove_ocr_decorations=False))

    assert pages[0].blocks == [native]
    assert pages[1].blocks == [ocr]


def test_removes_identical_image_repeated_as_page_decoration() -> None:
    ornament_path = Path("repeated-ornament.png")
    picture_path = Path("picture.png")
    pages = [
        Page(
            number,
            600,
            800,
            PageKind.NATIVE,
            [
                ImageBlock(
                    BoundingBox(100, 100, 500, 300),
                    number,
                    ornament_path,
                    400,
                    200,
                ),
                ImageBlock(
                    BoundingBox(100, 350, 500, 650),
                    number,
                    picture_path.with_stem(f"picture-{number}"),
                    400,
                    300,
                ),
            ],
        )
        for number in range(1, 6)
    ]

    clean_document(pages, ConversionConfig())

    assert all(
        [item.image_path for item in page.blocks]
        == [picture_path.with_stem(f"picture-{page.number}")]
        for page in pages
    )
