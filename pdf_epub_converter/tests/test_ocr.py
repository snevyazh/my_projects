from pathlib import Path
from subprocess import CompletedProcess

from pdf2epub.analyzer import PageAnalysis
from pdf2epub.models import PageKind
from pdf2epub.ocr import compress_page_ranges, ocr_pdf, pages_requiring_ocr


def test_compress_page_ranges() -> None:
    assert compress_page_ranges([1, 2, 3, 6, 9, 10]) == "1-3,6,9-10"
    assert compress_page_ranges([]) == ""


def test_scanned_page_with_stray_text_still_requires_ocr() -> None:
    analysis = PageAnalysis(1, 600, 800, 60, 1, 1, 0.95, 0.01, PageKind.SCANNED)
    assert pages_requiring_ocr([analysis]) == [1]


def test_ocr_uses_fast_intermediate_pdf_settings(tmp_path: Path, monkeypatch) -> None:
    analysis = PageAnalysis(1, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"pdf")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)
    result = ocr_pdf(tmp_path / "input.pdf", [analysis], tmp_path, "rus")
    assert result.performed
    assert "--output-type" in commands[0]
    assert commands[0][commands[0].index("--output-type") + 1] == "pdf"
    assert commands[0][commands[0].index("--optimize") + 1] == "0"
