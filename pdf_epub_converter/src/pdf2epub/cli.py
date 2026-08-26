from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .logging_utils import configure_logging
from .pipeline import SUPPORTED_INPUT_SUFFIXES, convert_document

app = typer.Typer(
    name="pdf2epub",
    help="Convert native, scanned, or mixed PDF/DjVu books to clean reflowable EPUB.",
    no_args_is_help=True,
)
console = Console()


def discover_documents(directory: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in directory.glob(pattern)
        if path.is_file() and path.suffix.casefold() in SUPPORTED_INPUT_SUFFIXES
    )


def output_for(source: Path, input_root: Path | None, output: Path | None) -> Path:
    if input_root is None:
        if output is None:
            return source.with_suffix(".epub")
        if output.suffix.casefold() == ".epub":
            return output
        return output / source.with_suffix(".epub").name
    root = output or input_root
    relative = source.relative_to(input_root).with_suffix(".epub")
    return root / relative


@app.command()
def main(
    input_path: Annotated[Path, typer.Argument(help="PDF/DjVu file or directory of books")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output EPUB or directory")] = None,
    recursive: Annotated[bool, typer.Option("--recursive", "-r", help="Recurse into directories")] = False,
    languages: Annotated[str, typer.Option("--languages", "-l", help="Tesseract languages joined by +")] = "rus+eng+heb",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing EPUB files")] = False,
    keep_temp: Annotated[bool, typer.Option("--keep-temp", help="Retain per-book working files")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    no_cover: Annotated[bool, typer.Option("--no-cover", help="Do not generate a cover")] = False,
    no_images: Annotated[
        bool, typer.Option("--no-images", help="Do not include source illustrations")
    ] = False,
    title: Annotated[str | None, typer.Option("--title", help="Override title (single file only)")] = None,
    author: Annotated[str | None, typer.Option("--author", help="Override author (single file only)")] = None,
) -> None:
    source = input_path.expanduser().resolve()
    resolved_output = output.expanduser().resolve() if output else None
    if not source.exists():
        raise typer.BadParameter(f"Input does not exist: {source}")
    if source.is_dir() and (title or author):
        raise typer.BadParameter("--title and --author can only be used with a single PDF")
    if source.is_dir() and resolved_output and resolved_output.suffix.casefold() == ".epub":
        raise typer.BadParameter("Directory input requires an output directory, not an .epub path")
    inputs = discover_documents(source, recursive) if source.is_dir() else [source]
    if not inputs:
        console.print("[yellow]No PDF or DjVu files found.[/yellow]")
        raise typer.Exit(0)
    log_root = resolved_output if resolved_output and resolved_output.suffix.casefold() != ".epub" else (
        resolved_output.parent if resolved_output else (source if source.is_dir() else source.parent)
    )
    logger = configure_logging(verbose, log_root / "pdf2epub.log")
    successful = 0
    failures: list[tuple[Path, str]] = []
    for index, document in enumerate(inputs, 1):
        target = output_for(document, source if source.is_dir() else None, resolved_output)
        console.print(f"\n[bold][{index}/{len(inputs)}][/bold] {document}")
        try:
            result = convert_document(
                document,
                target,
                languages=languages,
                title=title,
                author=author,
                cover=not no_cover,
                save_images=not no_images,
                keep_temp=keep_temp,
                force=force,
                logger=logger,
            )
            successful += 1
            console.print(
                f"  pages: {result.pages}\n"
                f"  native-text pages: {result.native_pages}\n"
                f"  OCR pages: {result.ocr_pages}\n"
                f"  images: {result.images}\n"
                f"  chapters: {result.chapters}\n"
                f"  output: {result.output_path}\n"
                "  status: [green]OK[/green]"
            )
            if result.temp_path:
                console.print(f"  temporary files: {result.temp_path}")
        except Exception as exc:
            failures.append((document, str(exc)))
            logger.exception("Conversion failed for %s", document) if verbose else logger.error(str(exc))
            console.print(f"  status: [red]FAILED[/red]\n  reason: {exc}")
    console.print(
        f"\nCompleted: {len(inputs)}\nSuccessful: {successful}\nFailed: {len(failures)}"
    )
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
