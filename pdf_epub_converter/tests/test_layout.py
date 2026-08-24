from pathlib import Path

from pdf2epub.layout import associate_image_captions, is_probably_multicolumn, sort_reading_order
from pdf2epub.models import BoundingBox, ImageBlock, Page, PageKind, TextBlock


def text(value: str, bbox: tuple[float, float, float, float]) -> TextBlock:
    return TextBlock(value, BoundingBox(*bbox), 10, "Serif", 1)


def test_reading_order_uses_vertical_position_then_left() -> None:
    image = ImageBlock(BoundingBox(20, 200, 300, 400), 1, Path("image.jpg"), 280, 200)
    blocks = [text("second", (30, 100, 500, 130)), image, text("first", (30, 20, 500, 50))]
    assert [getattr(item, "text", "image") for item in sort_reading_order(blocks)] == [
        "first",
        "second",
        "image",
    ]


def test_warns_for_obvious_two_column_geometry() -> None:
    blocks = [
        text("left column paragraph long enough", (30, 100, 280, 180)),
        text("right column paragraph long enough", (320, 100, 570, 180)),
        text("left column another paragraph long", (30, 200, 280, 280)),
        text("right column another paragraph long", (320, 200, 570, 280)),
    ]
    assert is_probably_multicolumn(Page(1, 600, 800, PageKind.NATIVE, blocks))


def test_associates_nearby_caption_without_losing_text() -> None:
    image = ImageBlock(BoundingBox(100, 100, 500, 400), 1, Path("image.jpg"), 400, 300)
    caption = TextBlock(
        "Figure 1. A landscape",
        BoundingBox(180, 408, 420, 425),
        9,
        "Serif",
        1,
        centered=True,
    )
    body = text("Body paragraph long enough to remain", (50, 500, 550, 540))
    page = Page(1, 600, 800, PageKind.MIXED, [image, caption, body])
    associate_image_captions(page)
    assert image.caption == "Figure 1. A landscape"
    assert page.blocks == [image, body]
