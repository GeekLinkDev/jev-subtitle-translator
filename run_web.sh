#!/bin/bash
# Start the Jev Subtitle Translator web UI

set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -e ".[web]"

echo "Open your browser at: http://127.0.0.1:8000"
exec .venv/bin/uvicorn --factory jev_subtitle_translator.web:create_app --reload --host 127.0.0.1 --port 8000
