from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from statistics import median

from .config import ConversionConfig
from .models import ImageBlock, Page, TextBlock

_ROMAN = r"(?=[MDCLXVI]+\b)M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_PAGE_NUMBER = re.compile(rf"^\s*(?:[-–—]\s*)?(?:\d{{1,5}}|{_ROMAN})(?:\s*[-–—])?\s*$", re.I)
_WORD = r"[A-Za-zÀ-ÖØ-öø-ÿĀ-žА-Яа-яЁёІіЇїЄєҐґ]+"
_LINE_HYPHEN = re.compile(rf"(?P<left>{_WORD})-\s*\n\s*(?P<right>{_WORD})")
_PRESERVED_PREFIXES = {"well", "self", "long", "short", "high", "low", "e", "non", "pre", "post"}
_OCR_WORD = re.compile(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ]+")


def _has_latin(value: str) -> bool:
    return any("LATIN" in unicodedata.name(character, "") for character in value)


def _has_cyrillic(value: str) -> bool:
    return any("CYRILLIC" in unicodedata.name(character, "") for character in value)


def _looks_like_mixed_script_ornament(text: str) -> bool:
    """Catch ornamental glyphs OCR'd as short, uppercase Latin/Cyrillic words."""
    words = _OCR_WORD.findall(text)
    mixed_words = [word for word in words if _has_latin(word) and _has_cyrillic(word)]
    letters = [character for character in text if character.isalpha()]
    cased = [character for character in letters if character.lower() != character.upper()]
    uppercase_ratio = (
        sum(character.isupper() for character in cased) / len(cased) if cased else 0.0
    )
    return (
        len(words) >= 3
        and len(mixed_words) >= 2
        and max(map(len, words), default=0) <= 8
        and uppercase_ratio >= 0.65
    )


def _looks_like_repeated_ornament(text: str) -> bool:
    compact = "".join(character.casefold() for character in text if character.isalpha())
    if len(compact) < 10:
        return False
    unique_ratio = len(set(compact)) / len(compact)
    bigrams = [compact[index : index + 2] for index in range(len(compact) - 1)]
    repeated_bigram_ratio = max(Counter(bigrams).values(), default=0) / len(bigrams)
    return unique_ratio <= 0.25 or (
        unique_ratio <= 0.5 and repeated_bigram_ratio >= 0.4
    )


def _looks_like_symbol_ornament(text: str) -> bool:
    visible = [character for character in text if not character.isspace()]
    if len(visible) < 3:
        return False
    symbols = [
        character
        for character in visible
        if unicodedata.category(character)[:1] in {"P", "S"}
    ]
    alphanumeric = sum(character.isalnum() for character in visible)
    return len(symbols) >= 3 and (
        len(symbols) / len(visible) >= 0.45 or alphanumeric <= 2
    )


def is_ocr_decoration_text(text: str) -> bool:
    """Identify high-confidence OCR renderings of rules, flourishes, and ornaments."""
    candidate = " ".join(text.split())
    if not candidate:
        return False
    return (
        _looks_like_symbol_ornament(candidate)
        or _looks_like_repeated_ornament(candidate)
        or _looks_like_mixed_script_ornament(candidate)
    )


def remove_ocr_decoration_lines(text: str) -> str:
    """Remove decorative lines without sacrificing real text sharing an OCR block."""
    return "\n".join(
        line for line in text.splitlines() if not is_ocr_decoration_text(line)
    ).strip()


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


def find_repeated_image_paths(pages: list[Page], config: ConversionConfig) -> set[Path]:
    """Find identical images repeated like page furniture rather than illustrations."""
    counts: Counter[Path] = Counter()
    for page in pages:
        counts.update(
            {
                block.image_path
                for block in page.blocks
                if isinstance(block, ImageBlock)
            }
        )
    threshold = max(
        config.repeated_image_min_pages,
        int(len(pages) * config.repeated_image_threshold + 0.999),
    )
    return {path for path, count in counts.items() if count >= threshold}


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
    repeated_images = find_repeated_image_paths(pages, config)
    for page in pages:
        cleaned = []
        for block in page.blocks:
            if isinstance(block, ImageBlock) and block.image_path in repeated_images:
                continue
            if isinstance(block, TextBlock):
                if is_page_number(block, page, config):
                    continue
                in_margin = block.bbox.y1 <= page.height * config.header_region_ratio or block.bbox.y0 >= page.height * (
                    1 - config.footer_region_ratio
                )
                if in_margin and normalize_repeated_text(block.text) in repeated:
                    continue
                if block.source == "ocr" and config.remove_ocr_decorations:
                    block.text = remove_ocr_decoration_lines(block.text)
                block.text = join_wrapped_lines(block.text)
                if not block.text:
                    continue
            cleaned.append(block)
        page.blocks = cleaned
        _merge_continuations(page, config)
    return pages
