#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
streamlit_bin="$project_dir/.venv/bin/streamlit"

if [[ ! -x "$streamlit_bin" ]]; then
    echo "Streamlit is not installed in $project_dir/.venv"
    echo "Run: .venv/bin/python -m pip install -e '.[ui]'"
    exit 1
fi

cd "$project_dir"
exec "$streamlit_bin" run "$project_dir/app.py"

