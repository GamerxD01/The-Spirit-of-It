"""Speech-to-text with faster-whisper (open-weight Whisper, runs on CPU)."""
import threading
from dataclasses import dataclass

from . import config


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list


_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE,
            )
    return _model


def transcribe(path: str, language: str | None = None) -> Transcript:
    model = _load()
    segs, info = model.transcribe(
        path,
        language=language or None,
        vad_filter=True,              # skip long silences between sentences
        beam_size=5,
        # Hindi/Awadhi elders code-switch constantly; a short prompt nudges Whisper toward Devanagari.
        initial_prompt="यह दादी की कहानी है।" if (language or "hi") == "hi" else None,
    )
    out = [Segment(s.start, s.end, s.text.strip()) for s in segs if s.text.strip()]
    return Transcript(language=info.language, duration=info.duration, segments=out)
