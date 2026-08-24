"""Structured PDF and DjVu to reflowable EPUB conversion."""

from .config import ConversionConfig
from .pipeline import ConversionResult, convert_document, convert_djvu, convert_pdf

__all__ = [
    "ConversionConfig",
    "ConversionResult",
    "convert_document",
    "convert_djvu",
    "convert_pdf",
]
__version__ = "0.1.0"
