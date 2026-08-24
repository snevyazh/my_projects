from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .config import ConversionConfig
from .models import Page, TextBlock

_ROMAN = r"(?=[MDCLXVI]+\b)M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_PAGE_NUMBER = re.compile(rf"^\s*(?:[-–—]\s*)?(?:\d{{1,5}}|{_ROMAN})(?:\s*[-–—])?\s*$", re.I)
_WORD = r"[A-Za-zÀ-ÖØ-öø-ÿĀ-žА-Яа-яЁёІіЇїЄєҐґ]+"
_LINE_HYPHEN = re.compile(rf"(?P<left>{_WORD})-\s*\n\s*(?P<right>{_WORD})")
_PRESERVED_PREFIXES = {"well", "self", "long", "short", "high", "low", "e", "non", "pre", "post"}


def normalize_repeated_text(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return re.sub(r"\d+", "#", normalized).strip(" -–—|•")


def is_page_number(block: TextBlock, page: Page, config: ConversionConfig) -> bool:
    in_margin = block.bbox.y1 <= page.height * config.header_region_ratio or block.bbox.y0 >= page.height * (
        1 - config.footer_region_ratio
    )
    return in_margin and bool(_PAGE_NUMBER.fullmatch(block.text))


def find_repeated_margin_text(pages: list[Page], config: ConversionConfig) -> set[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        keys_on_page: set[str] = set()
        for block in page.blocks:
            if not isinstance(block, TextBlock):
                continue
            in_margin = block.bbox.y1 <= page.height * config.header_region_ratio or block.bbox.y0 >= page.height * (
                1 - config.footer_region_ratio
            )
            if in_margin and len(block.text) <= 160:
                key = normalize_repeated_text(block.text)
                if key:
                    keys_on_page.add(key)
        counts.update(keys_on_page)
    threshold = max(
        config.repeated_header_min_pages,
        int(len(pages) * config.repeated_header_threshold + 0.999),
    )
    return {text for text, count in counts.items() if count >= threshold}


def repair_hyphenation(text: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        left, right = match.group("left"), match.group("right")
        if left.casefold() in _PRESERVED_PREFIXES:
            return f"{left}-{right}"
        # Lowercase continuation is the strongest language-independent signal available.
        if right[:1].islower() and len(left) >= 3:
            return left + right
        return f"{left}- {right}"

    return _LINE_HYPHEN.sub(replacement, text)


def join_wrapped_lines(text: str) -> str:
    text = repair_hyphenation(text)
    paragraphs = re.split(r"\n\s*\n", text)
    joined: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if lines:
            joined.append(" ".join(lines))
    return "\n\n".join(joined)


def _merge_continuations(page: Page, config: ConversionConfig) -> None:
    output = []
    for block in page.blocks:
        if not isinstance(block, TextBlock) or not output or not isinstance(output[-1], TextBlock):
            output.append(block)
            continue
        previous = output[-1]
        font = median([size for size in (previous.font_size, block.font_size) if size]) if (
            previous.font_size or block.font_size
        ) else 10.0
        gap = block.bbox.y0 - previous.bbox.y1
        aligned = abs(block.bbox.x0 - previous.bbox.x0) <= config.indent_tolerance
        same_style = not previous.font_size or not block.font_size or abs(previous.font_size - block.font_size) <= 1.0
        continuation = not re.search(r"[.!?…:;][\"'»”)]?$", previous.text)
        if aligned and same_style and -1 <= gap <= font * config.paragraph_gap_multiplier and continuation:
            previous.text = f"{previous.text} {block.text}".strip()
            previous.bbox = type(previous.bbox)(
                min(previous.bbox.x0, block.bbox.x0),
                min(previous.bbox.y0, block.bbox.y0),
                max(previous.bbox.x1, block.bbox.x1),
                max(previous.bbox.y1, block.bbox.y1),
            )
        else:
            output.append(block)
    page.blocks = output


def clean_document(pages: list[Page], config: ConversionConfig) -> list[Page]:
    repeated = find_repeated_margin_text(pages, config)
    for page in pages:
        cleaned = []
        for block in page.blocks:
            if isinstance(block, TextBlock):
                if is_page_number(block, page, config):
                    continue
                in_margin = block.bbox.y1 <= page.height * config.header_region_ratio or block.bbox.y0 >= page.height * (
                    1 - config.footer_region_ratio
                )
                if in_margin and normalize_repeated_text(block.text) in repeated:
                    continue
                block.text = join_wrapped_lines(block.text)
                if not block.text:
                    continue
            cleaned.append(block)
        page.blocks = cleaned
        _merge_continuations(page, config)
    return pages

