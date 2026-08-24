from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversionConfig:
    """Centralized, conservative conversion heuristics."""

    min_native_chars: int = 100
    scanned_image_coverage: float = 0.65
    mixed_image_coverage: float = 0.08
    header_region_ratio: float = 0.12
    footer_region_ratio: float = 0.12
    repeated_header_threshold: float = 0.4
    repeated_header_min_pages: int = 3
    min_image_width: int = 120
    min_image_height: int = 120
    minimum_image_area_ratio: float = 0.02
    maximum_scan_image_area_ratio: float = 0.90
    paragraph_gap_multiplier: float = 1.7
    indent_tolerance: float = 12.0
    chapter_font_multiplier: float = 1.25
    maximum_heading_characters: int = 100
    cover_dpi: int = 150
    illustration_dpi: int = 180
    suspicious_image_count: int = 500

