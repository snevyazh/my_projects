from __future__ import annotations

from statistics import median

from .models import Block, ImageBlock, Page, TextBlock


def sort_reading_order(blocks: list[Block]) -> list[Block]:
    """Single-column order; left position breaks ties on the same text line."""
    return sorted(blocks, key=lambda block: (round(block.bbox.y0, 1), block.bbox.x0, block.bbox.y1))


def is_probably_multicolumn(page: Page) -> bool:
    blocks = [block for block in page.blocks if isinstance(block, TextBlock) and len(block.text) > 30]
    if len(blocks) < 4:
        return False
    widths = [block.bbox.width for block in blocks]
    narrow = [block for block in blocks if block.bbox.width < page.width * 0.48]
    if len(narrow) < 4 or median(widths) >= page.width * 0.55:
        return False
    left = [block for block in narrow if block.bbox.x1 <= page.width * 0.58]
    right = [block for block in narrow if block.bbox.x0 >= page.width * 0.42]
    return len(left) >= 2 and len(right) >= 2


def reconstruct_layout(pages: list[Page]) -> list[Page]:
    for page in pages:
        page.blocks = sort_reading_order(page.blocks)
        if is_probably_multicolumn(page):
            page.warnings.append(
                f"Page {page.number} appears multi-column; reading order may be imperfect"
            )
    return pages


def associate_image_captions(page: Page) -> None:
    """Attach a short, nearby centered text block to its preceding illustration."""
    consumed: set[int] = set()
    for index, block in enumerate(page.blocks[:-1]):
        following = page.blocks[index + 1]
        if not isinstance(block, ImageBlock) or not isinstance(following, TextBlock):
            continue
        gap = following.bbox.y0 - block.bbox.y1
        overlaps_horizontally = (
            following.bbox.x1 >= block.bbox.x0 and following.bbox.x0 <= block.bbox.x1
        )
        if (
            0 <= gap <= max(24.0, (following.font_size or 10.0) * 2.0)
            and overlaps_horizontally
            and len(following.text.strip()) <= 180
            and (following.centered or following.bbox.width <= block.bbox.width * 1.1)
        ):
            block.caption = " ".join(following.text.split())
            consumed.add(index + 1)
    if consumed:
        page.blocks = [block for index, block in enumerate(page.blocks) if index not in consumed]
