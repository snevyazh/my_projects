from pdf2epub.analyzer import PageAnalysis
from pdf2epub.models import PageKind
from pdf2epub.ocr import compress_page_ranges, pages_requiring_ocr


def test_compress_page_ranges() -> None:
    assert compress_page_ranges([1, 2, 3, 6, 9, 10]) == "1-3,6,9-10"
    assert compress_page_ranges([]) == ""


def test_scanned_page_with_stray_text_still_requires_ocr() -> None:
    analysis = PageAnalysis(1, 600, 800, 60, 1, 1, 0.95, 0.01, PageKind.SCANNED)
    assert pages_requiring_ocr([analysis]) == [1]
