#!/usr/bin/env bash
# Dadi's Voice Archive - macOS / Linux launcher
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
echo "Make sure Ollama is running with a Gemma model:  ollama pull gemma3:4b"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
