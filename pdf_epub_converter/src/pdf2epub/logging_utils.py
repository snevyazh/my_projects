from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler


def configure_logging(verbose: bool = False, log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("pdf2epub")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    console = RichHandler(show_time=False, show_path=False, rich_tracebacks=verbose)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger
