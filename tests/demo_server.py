"""Run the real app with fake Whisper/Gemma (for screenshots / UI tests without model downloads)."""
import sys
import uvicorn
from tests import fakes
fakes.install()
from app.main import app  # noqa: E402
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8765, log_level="warning")
