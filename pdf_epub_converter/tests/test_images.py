from pdf2epub.config import ConversionConfig
from pdf2epub.images import is_meaningful_image_placement
from pdf2epub.models import BoundingBox


def test_keeps_substantial_picture() -> None:
    assert is_meaningful_image_placement(
        BoundingBox(100, 150, 500, 500), 600, 800, ConversionConfig()
    )


def test_rejects_horizontal_ornament_even_when_it_spans_the_page() -> None:
    assert not is_meaningful_image_placement(
        BoundingBox(50, 600, 550, 630), 600, 800, ConversionConfig()
    )


def test_rejects_vertical_border_and_small_icon() -> None:
    config = ConversionConfig()
    assert not is_meaningful_image_placement(
        BoundingBox(20, 50, 55, 750), 600, 800, config
    )
    assert not is_meaningful_image_placement(
        BoundingBox(270, 380, 330, 440), 600, 800, config
    )
