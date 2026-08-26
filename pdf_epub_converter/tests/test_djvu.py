from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from pdf2epub.djvu import (
    DjVuConversionError,
    DjVuDependencyError,
    check_djvu_dependencies,
    djvu_page_count,
    djvu_page_to_pdf,
    djvu_to_pdf,
)


def test_reports_exact_missing_djvu_dependencies(monkeypatch) -> None:
    monkeypatch.setattr("pdf2epub.djvu.shutil.which", lambda name: None)
    with pytest.raises(DjVuDependencyError, match="djvulibre-bin"):
        check_djvu_dependencies()


def test_reads_djvu_page_count(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pdf2epub.djvu.shutil.which", lambda name: f"/usr/bin/{name}")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        return CompletedProcess(command, 0, "402\n", "")

    monkeypatch.setattr("pdf2epub.djvu.subprocess.run", fake_run)
    source = tmp_path / "book.djvu"

    assert djvu_page_count(source) == 402
    assert commands == [["djvused", "-e", "n", str(source)]]


def test_renders_one_djvu_page_to_pdf(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pdf2epub.djvu.shutil.which", lambda name: f"/usr/bin/{name}")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"page")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.djvu.subprocess.run", fake_run)
    source = tmp_path / "book.djvu"
    target = tmp_path / "page.pdf"

    assert djvu_page_to_pdf(source, 17, target) == target
    assert commands == [
        [
            "ddjvu",
            "-subsample=2",
            "-page=17",
            "-format=pdf",
            str(source),
            str(target),
        ]
    ]


def test_djvu_to_pdf_runs_direct_raster_pdf_conversion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("pdf2epub.djvu.shutil.which", lambda name: f"/usr/bin/{name}")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"document")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("pdf2epub.djvu.subprocess.run", fake_run)
    result = djvu_to_pdf(tmp_path / "book.djvu", tmp_path)
    assert result == tmp_path / "djvu-source.pdf"
    assert commands == [
        [
            "ddjvu",
            "-subsample=2",
            "-format=pdf",
            str(tmp_path / "book.djvu"),
            str(result),
        ]
    ]


def test_djvu_conversion_surfaces_tool_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("pdf2epub.djvu.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "pdf2epub.djvu.subprocess.run",
        lambda command, **kwargs: CompletedProcess(command, 1, "", "broken DjVu"),
    )
    with pytest.raises(DjVuConversionError, match="broken DjVu"):
        djvu_to_pdf(tmp_path / "broken.djvu", tmp_path)
