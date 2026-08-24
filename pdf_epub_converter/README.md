# pdf2epub

`pdf2epub` converts ordinary text, scanned, and mixed PDF books into reflowable EPUB 3 files. It deliberately reconstructs text, chapters, and illustrations instead of wrapping page screenshots or delegating conversion to Calibre.

## What v1 does

- analyzes every page before OCR and classifies it as native, scanned, mixed, or empty;
- OCRs only scan-like pages with OCRmyPDF/Tesseract (`rus+eng+heb` by default);
- retains text/image bounding boxes, font information, page number, and text source in a structured book model;
- sorts normal single-column pages and warns about likely multi-column layouts;
- removes statistically repeated margin text and geometric page numbers;
- rebuilds wrapped paragraphs and repairs conservative Latin/Cyrillic line-end hyphenation;
- detects English, Russian, and Hebrew chapter markers plus strongly styled title-only headings;
- extracts meaningful embedded illustrations while rejecting tiny/repeated images and full-page scan backgrounds;
- creates a standards-structured EPUB with XHTML chapters, CSS, navigation, metadata, images, and an optional cover;
- processes directories independently, preserves relative directory structure, logs failures, and continues after a bad book.

This first version targets ordinary single-column books. Multi-column layouts, complex tables, magazines, and mathematical material are detected only heuristically and may need manual review.

## Requirements

- Python 3.12+
- OCRmyPDF and Tesseract for PDFs that need OCR
- the requested Tesseract language packs

On Debian/Ubuntu:

```bash
sudo apt install ocrmypdf tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng tesseract-ocr-heb
```

Native-text PDFs do not require the OCR executables at runtime.

## Install

### Linux

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e '.[dev]'
pytest
```

For the Streamlit interface:

```bash
python -m pip install -e '.[ui]'
```

### Windows

Install these prerequisites first:

1. Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/). Enable **Add Python to PATH** during installation.
2. Tesseract OCR with Russian, English, and Hebrew language data. Ensure `tesseract.exe` is available on `PATH`.
3. OCRmyPDF and its Windows prerequisites, following the [OCRmyPDF Windows installation guide](https://ocrmypdf.readthedocs.io/en/latest/installation.html#windows).

Open PowerShell in the project directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
```

The setup script creates `.venv-windows`, installs the project with development and UI dependencies, and runs the test suite. It does not install system OCR software automatically.

## Use

```bash
pdf2epub book.pdf
pdf2epub book.pdf --output ~/Books/EPUB/
pdf2epub ~/Books/PDF --output ~/Books/EPUB --recursive
pdf2epub book.pdf --languages rus+eng --title "My Book" --author "Author Name"
```

Run `pdf2epub --help` for all options. Existing EPUB files are not overwritten unless `--force` is supplied. Temporary work directories are removed even after failure unless `--keep-temp` is used. The input PDF is never modified.

## Streamlit interface

Start the browser interface with either:

```bash
pdf2epub-ui
# or
./start-linux.sh
```

On Windows, double-click:

```text
start-windows.bat
```

Alternatively, start it from PowerShell:

```powershell
.\.venv-windows\Scripts\pdf2epub-ui.exe
```

The interface opens at `http://127.0.0.1:8501`. Keep the terminal window open while using it. Press `Ctrl+C` in the terminal to stop the server.

The UI provides two input methods:

- **Local file selector** opens Zenity on Linux or the standard Windows file dialog through Tk and writes the EPUB to a selected local destination.
- **Browser upload** accepts a PDF through the browser and provides the converted EPUB as a download.

Install `zenity` on Linux for the preferred native dialog. If it is unavailable, the app attempts the Tk selector and always retains editable path fields as a fallback.

Windows and WSL virtual environments are not interchangeable. This project therefore uses `.venv` for Linux/WSL and `.venv-windows` for native Windows. Run `setup-windows.ps1` from Windows before using `start-windows.bat`.

## Pipeline

The public stages are independently usable and testable:

```text
analyze_pdf → ocr_pdf → extract_document → reconstruct_layout
            → clean_document → detect_chapters → build_epub
```

Heuristic thresholds live in `ConversionConfig`. External OCR failures name the missing binary or language pack and include the OCRmyPDF diagnostic. A `pdf2epub.log` file is written beside the output.

## Known v1 limits

- Password input is intentionally unsupported; encrypted PDFs fail clearly.
- Embedded PDF images are preserved directly where possible. Illustrations baked into a full-page scan are not yet segmented from the scan background.
- OCR confidence is not currently available from OCRmyPDF's PDF text layer, so low-confidence warnings cannot be emitted reliably.
- Chapter detection is conservative by design: uncertain headings remain in a single chapter instead of causing excessive splits.
