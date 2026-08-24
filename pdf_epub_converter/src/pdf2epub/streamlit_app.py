from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

from pdf2epub.logging_utils import configure_logging
from pdf2epub.pipeline import ConversionResult, convert_pdf


def clean_local_path(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    return os.path.normpath(os.path.expanduser(value)) if value else ""


def choose_with_zenity(*options: str) -> tuple[bool, str | None]:
    """Return (available, selection) for a native Linux Zenity dialog."""
    if os.name == "nt":
        return False, None
    executable = shutil.which("zenity")
    if not executable:
        return False, None
    result = subprocess.run(
        [executable, "--file-selection", *options],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        return True, result.stdout.rstrip("\r\n") or None
    if result.returncode == 1:  # Zenity uses 1 when the dialog is cancelled.
        return True, None
    raise RuntimeError(result.stderr.strip() or "Zenity could not open the dialog")


def _tk_dialog(*, save: bool, initial_name: str = "") -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        if save:
            selected = filedialog.asksaveasfilename(
                parent=root,
                initialfile=initial_name,
                defaultextension=".epub",
                filetypes=[("EPUB books", "*.epub"), ("All files", "*.*")],
            )
        else:
            selected = filedialog.askopenfilename(
                parent=root,
                filetypes=[("PDF documents", "*.pdf"), ("All files", "*.*")],
            )
    finally:
        root.destroy()
    return selected or None


def choose_pdf_file() -> str | None:
    available, selected = choose_with_zenity(
        "--title=Choose a PDF book", "--file-filter=PDF documents | *.pdf"
    )
    return selected if available else _tk_dialog(save=False)


def choose_save_file(initial_name: str) -> str | None:
    options = [
        "--save",
        "--confirm-overwrite",
        "--title=Choose EPUB destination",
        "--file-filter=EPUB books | *.epub",
    ]
    if initial_name:
        options.append(f"--filename={initial_name}")
    available, selected = choose_with_zenity(*options)
    return selected if available else _tk_dialog(save=True, initial_name=initial_name)


def default_output_path(source: Path) -> Path:
    return source.with_suffix(".epub")


def _show_result(result: ConversionResult, epub_bytes: bytes | None = None) -> None:
    st.success("Conversion completed successfully")
    first, second, third, fourth = st.columns(4)
    first.metric("Pages", result.pages)
    second.metric("OCR pages", result.ocr_pages)
    third.metric("Images", result.images)
    fourth.metric("Chapters", result.chapters)
    st.code(str(result.output_path), language=None)
    if result.warnings:
        with st.expander(f"Warnings ({len(result.warnings)})"):
            for warning in result.warnings:
                st.warning(warning)
    if epub_bytes is not None:
        st.download_button(
            "Download EPUB",
            data=epub_bytes,
            file_name=result.output_path.name,
            mime="application/epub+zip",
            type="primary",
            use_container_width=True,
        )


def _conversion_options() -> dict[str, object]:
    st.subheader("Conversion options")
    languages = st.text_input("OCR languages", value="rus+eng+heb")
    left, right = st.columns(2)
    title = left.text_input("Title override", placeholder="Use PDF metadata")
    author = right.text_input("Author override", placeholder="Use PDF metadata")
    cover = st.checkbox("Generate cover", value=True)
    force = st.checkbox("Overwrite an existing EPUB", value=False)
    return {
        "languages": languages.strip() or "rus+eng+heb",
        "title": title.strip() or None,
        "author": author.strip() or None,
        "cover": cover,
        "force": force,
    }


def _render_local_mode(options: dict[str, object]) -> None:
    left, right = st.columns([1, 3])
    if left.button("Choose PDF…", use_container_width=True):
        try:
            selected = choose_pdf_file()
            if selected:
                st.session_state["local_pdf_path"] = selected
                st.session_state["local_epub_path"] = str(default_output_path(Path(selected)))
        except Exception as exc:
            st.error(f"Could not open the file selector: {exc}")
    right.text_input(
        "PDF path",
        key="local_pdf_path",
        placeholder="/path/to/book.pdf",
        label_visibility="collapsed",
    )

    source_value = clean_local_path(st.session_state.get("local_pdf_path", ""))
    suggested = str(default_output_path(Path(source_value))) if source_value else "book.epub"
    output_left, output_right = st.columns([1, 3])
    if output_left.button("Save as…", use_container_width=True):
        try:
            selected = choose_save_file(st.session_state.get("local_epub_path", suggested))
            if selected:
                st.session_state["local_epub_path"] = selected
        except Exception as exc:
            st.error(f"Could not open the save selector: {exc}")
    output_right.text_input(
        "EPUB path",
        key="local_epub_path",
        value=st.session_state.get("local_epub_path", suggested),
        label_visibility="collapsed",
    )

    if st.button("Convert PDF", type="primary", use_container_width=True, key="convert_local"):
        source = Path(clean_local_path(st.session_state.get("local_pdf_path", "")))
        output = Path(clean_local_path(st.session_state.get("local_epub_path", "")))
        if not source.is_file() or source.suffix.casefold() != ".pdf":
            st.error("Select an existing PDF file first.")
            return
        if not output.name:
            st.error("Choose an EPUB destination.")
            return
        if output.suffix.casefold() != ".epub":
            output = output.with_suffix(".epub")
        try:
            with st.status("Converting book…", expanded=True) as status:
                st.write("Analyzing pages and selecting OCR work…")
                logger = configure_logging(True, output.parent / "pdf2epub.log")
                result = convert_pdf(source, output, logger=logger, **options)
                status.update(label="Conversion complete", state="complete", expanded=False)
            _show_result(result)
        except Exception as exc:
            st.exception(exc)


def _render_upload_mode(options: dict[str, object]) -> None:
    upload = st.file_uploader("Choose a PDF book", type=["pdf"], accept_multiple_files=False)
    if st.button(
        "Convert uploaded PDF",
        type="primary",
        use_container_width=True,
        disabled=upload is None,
        key="convert_upload",
    ):
        assert upload is not None
        try:
            with tempfile.TemporaryDirectory(prefix="pdf2epub-ui-") as temporary:
                work_dir = Path(temporary)
                source = work_dir / Path(upload.name).name
                output = work_dir / source.with_suffix(".epub").name
                source.write_bytes(upload.getvalue())
                with st.status("Converting uploaded book…", expanded=True) as status:
                    st.write("Analyzing pages and selecting OCR work…")
                    result = convert_pdf(source, output, logger=configure_logging(True), **options)
                    epub_bytes = output.read_bytes()
                    status.update(label="Conversion complete", state="complete", expanded=False)
                st.session_state["uploaded_result"] = result
                st.session_state["uploaded_epub"] = epub_bytes
                st.session_state["uploaded_epub_name"] = output.name
        except Exception as exc:
            st.exception(exc)

    result = st.session_state.get("uploaded_result")
    epub_bytes = st.session_state.get("uploaded_epub")
    if result and epub_bytes:
        # Replace the expired temporary path with the user-facing download name.
        display_result = ConversionResult(
            input_path=result.input_path,
            output_path=Path(st.session_state["uploaded_epub_name"]),
            pages=result.pages,
            native_pages=result.native_pages,
            ocr_pages=result.ocr_pages,
            images=result.images,
            chapters=result.chapters,
            warnings=result.warnings,
        )
        _show_result(display_result, epub_bytes)


def render_app() -> None:
    st.set_page_config(page_title="PDF → EPUB", page_icon="📚", layout="centered")
    st.title("PDF → EPUB Converter")
    st.caption("Reflowable text · selective OCR · chapter detection · preserved illustrations")

    mode = st.radio(
        "Input method",
        ["Local file selector", "Browser upload"],
        horizontal=True,
        help="The native selector works when Streamlit runs on your own computer.",
    )
    options = _conversion_options()
    st.divider()
    if mode == "Local file selector":
        _render_local_mode(options)
    else:
        _render_upload_mode(options)


if __name__ == "__main__":
    render_app()
