"""Structured PDF to reflowable EPUB conversion."""

from .config import ConversionConfig
from .pipeline import ConversionResult, convert_pdf

__all__ = ["ConversionConfig", "ConversionResult", "convert_pdf"]
__version__ = "0.1.0"

