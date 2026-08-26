from pathlib import Path

from pdf2epub.streamlit_app import _progress_callback, clean_local_path, default_output_path
from streamlit.testing.v1 import AppTest


def test_clean_local_path_expands_quotes_and_user(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/example")
    assert clean_local_path(" '~/Downloads/book.pdf' ") == "/home/example/Downloads/book.pdf"


def test_default_output_path_replaces_pdf_suffix() -> None:
    assert default_output_path(Path("/books/example.PDF")) == Path("/books/example.epub")


def test_progress_callback_reports_page_and_percentage() -> None:
    calls: list[tuple[float, str]] = []

    class ProgressBar:
        def progress(self, value: float, *, text: str) -> None:
            calls.append((value, text))

    _progress_callback(ProgressBar())(17, 40)

    assert calls == [(0.425, "Processing page 17 of 40 — 42.5%")]


def test_streamlit_app_renders_file_selection_modes() -> None:
    app = AppTest.from_file("../app.py").run(timeout=10)
    assert not app.exception
    assert app.title[0].value == "PDF/DjVu → EPUB Converter"
    assert app.radio[0].options == ["Local file selector", "Browser upload"]
    assert any(button.label == "Choose book…" for button in app.button)
    assert any(button.label == "Convert book" for button in app.button)
    assert any(checkbox.label == "Save pictures" for checkbox in app.checkbox)
    app.radio[0].set_value("Browser upload").run(timeout=10)
    assert not app.exception
    assert app.file_uploader[0].label == "Choose a PDF or DjVu book"
