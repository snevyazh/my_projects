#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
streamlit_bin="$project_dir/.venv-linux/bin/streamlit"

if [[ ! -x "$streamlit_bin" ]]; then
    echo "Linux virtual environment not found: $streamlit_bin"
    echo "Run the Linux setup commands in README.md first."
    exit 1
fi

cd "$project_dir"
exec "$streamlit_bin" run "$project_dir/app.py"
