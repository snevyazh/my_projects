from pathlib import Path
from subprocess import CompletedProcess

from pdf2epub.analyzer import PageAnalysis
from pdf2epub.models import PageKind
from pdf2epub.ocr import (
    OCRProcessingError,
    _failure_detail,
    compress_page_ranges,
    ocr_pdf,
    pages_requiring_ocr,
)


def test_compress_page_ranges() -> None:
    assert compress_page_ranges([1, 2, 3, 6, 9, 10]) == "1-3,6,9-10"
    assert compress_page_ranges([]) == ""


def test_scanned_page_with_stray_text_still_requires_ocr() -> None:
    analysis = PageAnalysis(1, 600, 800, 60, 1, 1, 0.95, 0.01, PageKind.SCANNED)
    assert pages_requiring_ocr([analysis]) == [1]


def test_unreliable_native_text_requires_ocr() -> None:
    analysis = PageAnalysis(
        1, 600, 800, 500, 5, 0, 0.0, 0.5, PageKind.MIXED, native_text_reliable=False
    )
    assert pages_requiring_ocr([analysis]) == [1]


def test_ocr_uses_fast_intermediate_pdf_settings(tmp_path: Path, monkeypatch) -> None:
    analysis = PageAnalysis(1, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
    (tmp_path / "input.pdf").write_bytes(b"input")
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"pdf")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)
    result = ocr_pdf(tmp_path / "input.pdf", [analysis], tmp_path, "rus")
    assert result.performed
    assert commands[0][commands[0].index("--jobs") + 1] == "2"
    assert "--skip-text" in commands[0]
    assert "--output-type" in commands[0]
    assert commands[0][commands[0].index("--oversample") + 1] == "300"
    assert commands[0][commands[0].index("--output-type") + 1] == "pdf"
    assert commands[0][commands[0].index("--optimize") + 1] == "0"


def test_ocr_forces_rasterization_for_unreliable_native_text(
    tmp_path: Path, monkeypatch
) -> None:
    analysis = PageAnalysis(
        1, 600, 800, 500, 5, 0, 0.0, 0.5, PageKind.MIXED, native_text_reliable=False
    )
    (tmp_path / "input.pdf").write_bytes(b"input")
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"pdf")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)

    ocr_pdf(tmp_path / "input.pdf", [analysis], tmp_path, "rus")

    assert "--force-ocr" in commands[0]


def test_ocr_retries_ghostscript_failure_with_one_worker(tmp_path: Path, monkeypatch) -> None:
    analysis = PageAnalysis(1, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"input")
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        if len(commands) == 1:
            return CompletedProcess(
                command,
                7,
                "",
                "Error: /undefinedfilename in (origin.pdf)\nGhostscript rasterizing failed",
            )
        Path(command[-1]).write_bytes(b"ocr")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)

    result = ocr_pdf(input_path, [analysis], tmp_path, "rus")

    assert result.pdf_path.name == "ocr-single-job.pdf"
    assert result.warnings == ("OCRmyPDF recovered after retrying with one worker.",)
    assert [command[command.index("--jobs") + 1] for command in commands] == ["2", "1"]


def test_ocr_leaves_failed_empty_page_unchanged(tmp_path: Path, monkeypatch) -> None:
    analyses = [
        PageAnalysis(number, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
        for number in (1, 2)
    ]
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"input")
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        if len(commands) < 3:
            return CompletedProcess(
                command,
                7,
                "",
                "2 [tesseract] Too few characters. Skipping this page\n"
                "2 [tesseract] Error during processing.",
            )
        Path(command[-1]).write_bytes(b"ocr")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)

    result = ocr_pdf(input_path, analyses, tmp_path, "rus")

    assert result.page_numbers == frozenset({1})
    assert commands[-1][commands[-1].index("--pages") + 1] == "1"
    assert result.warnings == (
        "Tesseract could not process OCR pages 2; they were left unchanged.",
    )


def test_ocr_repairs_invalid_pdf_and_retries(tmp_path: Path, monkeypatch) -> None:
    analysis = PageAnalysis(1, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"pdf")
    commands: list[list[str]] = []
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)
    monkeypatch.setattr("pdf2epub.ocr.shutil.which", lambda name: "/usr/bin/gs")

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        if Path(command[0]).name == "gs":
            output_argument = next(arg for arg in command if arg.startswith("-sOutputFile="))
            Path(output_argument.removeprefix("-sOutputFile=")).write_bytes(b"repaired")
            return CompletedProcess(command, 0, "", "")
        if len([item for item in commands if item[0] == "ocrmypdf"]) == 1:
            return CompletedProcess(command, 4, "", "Output file: The generated PDF is INVALID")
        Path(command[-1]).write_bytes(b"ocr")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.ocr.subprocess.run", fake_run)
    result = ocr_pdf(input_path, [analysis], tmp_path, "rus")

    assert result.performed
    assert result.pdf_path.name == "ocr-repaired.pdf"
    assert result.warnings == (
        "The source PDF contained malformed streams and was repaired before OCR.",
    )
    assert [Path(command[0]).name for command in commands] == ["ocrmypdf", "gs", "ocrmypdf"]
    assert commands[-1][-2] == str(tmp_path / "repaired-input.pdf")


def test_ocr_reports_missing_ghostscript_for_invalid_pdf(tmp_path: Path, monkeypatch) -> None:
    analysis = PageAnalysis(1, 600, 800, 0, 0, 1, 1.0, 0.0, PageKind.SCANNED)
    (tmp_path / "input.pdf").write_bytes(b"input")
    monkeypatch.setattr("pdf2epub.ocr.check_ocr_dependencies", lambda languages: None)
    monkeypatch.setattr("pdf2epub.ocr.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "pdf2epub.ocr.subprocess.run",
        lambda command, **kwargs: CompletedProcess(
            command, 4, "", "Output file: The generated PDF is INVALID"
        ),
    )

    try:
        ocr_pdf(tmp_path / "input.pdf", [analysis], tmp_path, "rus")
    except OCRProcessingError as exc:
        assert "Ghostscript (gs) is not installed" in str(exc)
    else:
        raise AssertionError("Expected OCRProcessingError")


def test_ocr_failure_detail_is_bounded_and_reports_signal() -> None:
    completed = CompletedProcess(["ocrmypdf"], -9, "", "x" * 5000)

    detail = _failure_detail(completed)

    assert detail.startswith("terminated by signal 9:")
    assert "1000 earlier log characters omitted" in detail
    assert len(detail) < 4100
