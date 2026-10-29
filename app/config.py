"""Settings. Everything is local: the only network address the app ever talks to is your own Ollama."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DVA_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "archive.db"

OLLAMA_URL = os.environ.get("DVA_OLLAMA_URL", "http://127.0.0.1:11434")
# Leave empty to auto-pick the first installed Gemma model (falls back to any installed model).
OLLAMA_MODEL = os.environ.get("DVA_MODEL", "")

WHISPER_MODEL = os.environ.get("DVA_WHISPER", "small")  # tiny / base / small / medium / large-v3
WHISPER_DEVICE = os.environ.get("DVA_WHISPER_DEVICE", "auto")  # auto / cpu / cuda
WHISPER_COMPUTE = os.environ.get("DVA_WHISPER_COMPUTE", "int8")


def ensure_dirs() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
