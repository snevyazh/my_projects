from pdf2epub.analyzer import classify_page
from pdf2epub.config import ConversionConfig
from pdf2epub.models import PageKind


def test_classifies_native_scanned_mixed_and_empty() -> None:
    config = ConversionConfig()
    assert classify_page(500, 5, 0.0, config) == PageKind.NATIVE
    assert classify_page(0, 0, 0.95, config) == PageKind.SCANNED
    assert classify_page(500, 5, 0.2, config) == PageKind.MIXED
    assert classify_page(0, 0, 0.0, config) == PageKind.EMPTY


def test_short_but_structured_text_is_native() -> None:
    assert classify_page(50, 3, 0.0, ConversionConfig()) == PageKind.NATIVE

