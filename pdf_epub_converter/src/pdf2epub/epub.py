from __future__ import annotations

import html
import re
from pathlib import Path

from .models import Book, Chapter, ImageBlock, TextBlock

CSS = """body { font-family: serif; line-height: 1.45; margin: 5%; }
h1 { text-align: center; margin: 2em 0 1.5em; }
p { margin: 0 0 .65em; text-align: justify; text-indent: 1.25em; }
figure { margin: 1.5em auto; text-align: center; page-break-inside: avoid; }
img { max-width: 100%; height: auto; }
figcaption { font-size: .9em; font-style: italic; margin-top: .5em; }
.front-matter p { text-indent: 0; }
"""


class EpubBuildError(RuntimeError):
    pass


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def _chapter_xhtml(chapter: Chapter, image_hrefs: dict[Path, str]) -> str:
    parts: list[str] = []
    heading_written = False
    for block in chapter.blocks:
        if isinstance(block, TextBlock):
            text = html.escape(block.text).replace("\n\n", "</p><p>")
            if block.is_heading and not heading_written:
                parts.append(f"<h1>{text}</h1>")
                heading_written = True
            else:
                direction = ' dir="rtl"' if re.search(r"[\u0590-\u05ff]", block.text) else ""
                parts.append(f"<p{direction}>{text}</p>")
        elif isinstance(block, ImageBlock) and block.image_path in image_hrefs:
            caption = (
                f"<figcaption>{html.escape(block.caption)}</figcaption>" if block.caption else ""
            )
            parts.append(
                f'<figure><img src="../{image_hrefs[block.image_path]}" alt="" />{caption}</figure>'
            )
    return "\n".join(parts) or "<p></p>"


def build_epub(book: Book, output_path: Path) -> Path:
    try:
        from ebooklib import epub
    except ImportError as exc:  # pragma: no cover
        raise EpubBuildError("EbookLib is required to build EPUB files") from exc

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        publication = epub.EpubBook()
        publication.set_identifier(book.metadata.identifier or book.metadata.title)
        publication.set_title(book.metadata.title)
        publication.set_language(book.metadata.language or "und")
        for author in book.metadata.authors:
            publication.add_author(author)
        if book.metadata.subject:
            publication.add_metadata("DC", "subject", book.metadata.subject)
        for keyword in book.metadata.keywords:
            publication.add_metadata("DC", "subject", keyword)

        style = epub.EpubItem(
            uid="style", file_name="styles/book.css", media_type="text/css", content=CSS
        )
        publication.add_item(style)

        image_hrefs: dict[Path, str] = {}
        image_paths = dict.fromkeys(
            block.image_path
            for chapter in book.chapters
            for block in chapter.blocks
            if isinstance(block, ImageBlock)
        )
        for index, image_path in enumerate(image_paths, 1):
            extension = image_path.suffix.lower() or ".jpg"
            href = f"images/image_{index:04d}{extension}"
            item = epub.EpubImage(
                uid=f"image_{index:04d}",
                file_name=href,
                media_type=(
                    "image/png" if extension == ".png" else "image/jpeg"
                ),
                content=image_path.read_bytes(),
            )
            publication.add_item(item)
            image_hrefs[image_path] = href

        if book.cover_path and book.cover_path.exists():
            publication.set_cover(
                _safe_name("cover" + book.cover_path.suffix.lower()),
                book.cover_path.read_bytes(),
                create_page=True,
            )

        chapter_items = []
        for index, chapter in enumerate(book.chapters, 1):
            item = epub.EpubHtml(
                title=chapter.title,
                file_name=f"text/chapter_{index:04d}.xhtml",
                lang=book.metadata.language or "und",
            )
            item.content = _chapter_xhtml(chapter, image_hrefs)
            item.add_item(style)
            publication.add_item(item)
            chapter_items.append(item)
        publication.toc = tuple(chapter_items)
        publication.add_item(epub.EpubNcx())
        publication.add_item(epub.EpubNav())
        publication.spine = ["nav", *chapter_items]
        epub.write_epub(str(output_path), publication, {})
        return output_path
    except EpubBuildError:
        raise
    except Exception as exc:
        raise EpubBuildError(f"Failed to write EPUB {output_path}: {exc}") from exc
