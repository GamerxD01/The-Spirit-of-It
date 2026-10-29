"""Tiny BM25 over transcript passages. No embedding model needed, works for Devanagari and English alike."""
import math
import re
from collections import Counter

_TOKEN = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)
_STOP = set(
    "the a an and or of to in on at is was were be been it that this what who when where why how did do does "
    "she he her his they them i you me my your about tell ever for with from as by had have has "
    "का की के है था थी थे और में से को ने भी तो यह वह जो एक पर हम".split()
)


def tokens(text: str) -> list[str]:
    return [t for t in (w.lower() for w in _TOKEN.findall(text)) if t not in _STOP and len(t) > 1]


def passages(segments: list[dict], window: int = 3) -> list[dict]:
    """Group consecutive Whisper segments of each story into overlapping passages."""
    by_story: dict[int, list[dict]] = {}
    for s in segments:
        by_story.setdefault(s["story_id"], []).append(s)
    out = []
    for sid, segs in by_story.items():
        segs.sort(key=lambda s: s["idx"])
        step = max(1, window - 1)
        for i in range(0, len(segs), step):
            chunk = segs[i : i + window]
            out.append(
                {
                    "story_id": sid,
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"],
                    "text": " ".join(c["text"] for c in chunk),
                    "extra": " ".join(c.get("extra", "") for c in chunk),
                }
            )
            if i + window >= len(segs):
                break
    return out


def bm25(query: str, docs: list[dict], k: int = 6, k1: float = 1.5, b: float = 0.75) -> list[dict]:
    q = tokens(query)
    if not q or not docs:
        return []
    toks = [tokens(d["text"] + " " + d.get("extra", "")) for d in docs]
    n = len(docs)
    avg = sum(len(t) for t in toks) / n or 1
    df = Counter(w for t in toks for w in set(t))
    scored = []
    for d, t in zip(docs, toks):
        tf = Counter(t)
        s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        if s > 0:
            scored.append({**d, "score": round(s, 3)})
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:k]
