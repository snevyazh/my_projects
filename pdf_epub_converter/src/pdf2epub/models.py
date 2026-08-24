from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeAlias


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height


class PageKind(StrEnum):
    NATIVE = "native"
    SCANNED = "scanned"
    MIXED = "mixed"
    EMPTY = "empty"


@dataclass(slots=True)
class TextBlock:
    text: str
    bbox: BoundingBox
    font_size: float | None
    font_name: str | None
    page_number: int
    source: Literal["native", "ocr"] = "native"
    bold: bool = False
    centered: bool = False
    is_heading: bool = False


@dataclass(slots=True)
class ImageBlock:
    bbox: BoundingBox
    page_number: int
    image_path: Path
    width: int
    height: int
    media_type: str = "image/jpeg"
    caption: str | None = None


Block: TypeAlias = TextBlock | ImageBlock


@dataclass(slots=True)
class Page:
    number: int
    width: float
    height: float
    kind: PageKind
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BookMetadata:
    title: str
    authors: list[str] = field(default_factory=list)
    language: str = "und"
    subject: str | None = None
    keywords: list[str] = field(default_factory=list)
    identifier: str | None = None


@dataclass(slots=True)
class Chapter:
    title: str
    blocks: list[Block]
    index: int


@dataclass(slots=True)
class Book:
    metadata: BookMetadata
    pages: list[Page]
    chapters: list[Chapter] = field(default_factory=list)
    cover_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

