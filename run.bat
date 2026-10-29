@echo off
REM Dadi's Voice Archive - Windows launcher
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo Make sure Ollama is running with a Gemma model:  ollama pull gemma3:4b
start "" http://127.0.0.1:8000
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
