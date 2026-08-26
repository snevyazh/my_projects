from __future__ import annotations

import re

_INVALID_XML_CHARACTER = re.compile(
    "[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
)


def has_invalid_xml_characters(value: str) -> bool:
    return _INVALID_XML_CHARACTER.search(value) is not None


def sanitize_xml_text(value: str) -> str:
    """Replace characters forbidden by XML 1.0 while retaining word boundaries."""
    return _INVALID_XML_CHARACTER.sub(" ", value)
