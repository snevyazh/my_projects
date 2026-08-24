from __future__ import annotations

import re
from statistics import median

from .config import ConversionConfig
from .models import Block, Chapter, Page, TextBlock

_EXPLICIT_CHAPTER = re.compile(
    r"^\s*(?:chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+)|глава\s+(?:\d+|[ivxlcdm]+|[а-яё]+)|פרק\s+[\dא-ת]+)(?:\s*[.:—–-].*)?$",
    re.IGNORECASE,
)


def body_font_size(pages: list[Page]) -> float:
    sizes = [
        block.font_size
        for page in pages
        for block in page.blocks
        if isinstance(block, TextBlock) and block.font_size and len(block.text) >= 40
    ]
    return median(sizes) if sizes else 10.0


def heading_score(block: TextBlock, page: Page, normal_size: float, config: ConversionConfig) -> int:
    text = " ".join(block.text.split())
    if not text or len(text) > config.maximum_heading_characters or "\n\n" in block.text:
        return 0
    if _EXPLICIT_CHAPTER.fullmatch(text):
        return 5
    score = 0
    if block.font_size and block.font_size >= normal_size * config.chapter_font_multiplier:
        score += 2
    if block.bold:
        score += 1
    if block.centered:
        score += 1
    if len(text) <= 60:
        score += 1
    if block.bbox.y0 <= page.height * 0.45:
        score += 1
    if text.endswith(('.', ',', ';')):
        score -= 2
    return score


def detect_chapters(pages: list[Page], config: ConversionConfig) -> list[Chapter]:
    normal_size = body_font_size(pages)
    ordered: list[Block] = [block for page in pages for block in page.blocks]
    heading_indices: list[int] = []
    page_by_number = {page.number: page for page in pages}
    for index, block in enumerate(ordered):
        if isinstance(block, TextBlock):
            score = heading_score(block, page_by_number[block.page_number], normal_size, config)
            if score >= 4:
                block.is_heading = True
                heading_indices.append(index)
    if not heading_indices:
        return [Chapter("Book", ordered, 1)] if ordered else []
    chapters: list[Chapter] = []
    if heading_indices[0] > 0:
        chapters.append(Chapter("Front Matter", ordered[: heading_indices[0]], 1))
    for position, start in enumerate(heading_indices):
        end = heading_indices[position + 1] if position + 1 < len(heading_indices) else len(ordered)
        heading = ordered[start]
        assert isinstance(heading, TextBlock)
        chapters.append(Chapter(" ".join(heading.text.split()), ordered[start:end], len(chapters) + 1))
    return chapters
