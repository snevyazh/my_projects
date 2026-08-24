from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Launch the packaged Streamlit application."""
    try:
        from streamlit.web import cli as streamlit_cli
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise SystemExit(
            "Streamlit UI dependencies are missing. Run: pip install -e '.[ui]'"
        ) from exc

    app_path = Path(__file__).with_name("streamlit_app.py")
    sys.argv = ["streamlit", "run", str(app_path), *sys.argv[1:]]
    raise SystemExit(streamlit_cli.main())

