"""Story pipeline: voice -> Whisper transcript -> Gemma translation + memory card. Plus grounded 'Ask'."""
import json
import logging

from . import asr, db, llm, search

log = logging.getLogger("dva")

LANG_NAMES = {"hi": "Hindi", "en": "English", "ur": "Urdu", "bn": "Bengali", "pa": "Punjabi", "mr": "Marathi",
              "gu": "Gujarati", "ta": "Tamil", "te": "Telugu", "ne": "Nepali", "es": "Spanish"}


def _set(story_id: int, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db.tx() as con:
        con.execute(f"UPDATE stories SET {cols} WHERE id = ?", (*fields.values(), story_id))


# ---------------------------------------------------------------- translation
TRANSLATE_SYS = (
    "You translate a grandmother's spoken memories from {lang} (often village Hindi/Awadhi, mixed with English words) "
    "into warm, plain English. Keep names, places, foods and song titles as they are (transliterated). "
    "Keep her voice: short sentences, no polishing into formal prose. Do not add anything she did not say. "
    'Return JSON: {{"lines": {{"<number>": "<english>"}}}} with one entry for every numbered line.'
)


def translate_segments(segs: list[dict], lang: str, batch: int = 20) -> dict[int, str]:
    out: dict[int, str] = {}
    lang_name = LANG_NAMES.get(lang, lang or "Hindi")
    for i in range(0, len(segs), batch):
        chunk = segs[i : i + batch]
        user = "\n".join(f"{s['idx']}. {s['text']}" for s in chunk)
        data = llm.chat_json(TRANSLATE_SYS.format(lang=lang_name), user)
        lines = data.get("lines", data) if isinstance(data, dict) else {}
        for s in chunk:
            t = lines.get(str(s["idx"])) if isinstance(lines, dict) else None
            if isinstance(t, str) and t.strip():
                out[s["idx"]] = t.strip()
    return out


# ---------------------------------------------------------------- memory card
CARD_SYS = (
    "You are a family archivist building an ofrenda (a remembrance altar) from a recorded story told by {name}. "
    "Read the story and return JSON with keys: "
    '"title" (a short evocative English title, max 8 words), '
    '"summary" (2-3 sentences in English, third person, past tense, only facts from the story), '
    '"people" (list of names or relations mentioned), "places" (list), "foods" (list), '
    '"songs" (list of songs, bhajans, lullabies or poems mentioned), '
    '"era" (approximate decade or period if it can be inferred, else ""), '
    '"keepsake" (the single most moving sentence from the story, quoted exactly in the original language). '
    "Never invent details. Empty lists are fine."
)


def memory_card(name: str, transcript: str, translation: str) -> dict:
    text = translation if translation else transcript
    user = f"ORIGINAL:\n{transcript[:6000]}\n\nENGLISH:\n{text[:6000]}"
    data = llm.chat_json(CARD_SYS.format(name=name), user)
    tags = {}
    for k in ("people", "places", "foods", "songs"):
        v = data.get(k) or []
        tags[k] = [str(x).strip() for x in v if str(x).strip()][:12] if isinstance(v, list) else []
    tags["era"] = str(data.get("era") or "").strip()
    tags["keepsake"] = str(data.get("keepsake") or "").strip()
    return {"title": str(data.get("title") or "").strip(), "summary": str(data.get("summary") or "").strip(), "tags": tags}


# ---------------------------------------------------------------- full pipeline
def process(story_id: int, language: str | None = None) -> None:
    with db.tx() as con:
        st = db.row(con.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone())
        elder = db.row(con.execute("SELECT * FROM elders WHERE id = ?", (st["elder_id"],)).fetchone())
    from . import config

    try:
        _set(story_id, status="transcribing", error="")
        tr = asr.transcribe(str(config.AUDIO_DIR / st["audio_file"]), language)
        with db.tx() as con:
            con.execute("DELETE FROM segments WHERE story_id = ?", (story_id,))
            con.executemany(
                "INSERT INTO segments (story_id, idx, start, end, text) VALUES (?,?,?,?,?)",
                [(story_id, i, s.start, s.end, s.text) for i, s in enumerate(tr.segments)],
            )
        transcript = "\n".join(s.text for s in tr.segments)
        _set(story_id, status="remembering", language=tr.language, duration=tr.duration, transcript=transcript)
    except Exception as e:  # noqa: BLE001
        log.exception("transcription failed")
        _set(story_id, status="error", error=f"Transcription failed: {e}")
        return
    remember(story_id, elder["name"])


def remember(story_id: int, name: str) -> None:
    """The Gemma half of the pipeline. Safe to re-run (e.g. after starting Ollama)."""
    try:
        _set(story_id, status="remembering", error="")
        with db.tx() as con:
            st = db.row(con.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone())
            segs = db.rows(con.execute("SELECT * FROM segments WHERE story_id = ? ORDER BY idx", (story_id,)))
        translation = ""
        if st["language"] != "en" and segs:
            tmap = translate_segments(segs, st["language"])
            with db.tx() as con:
                con.executemany("UPDATE segments SET translation = ? WHERE story_id = ? AND idx = ?",
                                [(t, story_id, i) for i, t in tmap.items()])
            translation = "\n".join(tmap.get(s["idx"], "") for s in segs).strip()
        card = memory_card(name, st["transcript"], translation)
        _set(story_id, status="done", translation=translation, title=card["title"] or "Untitled story",
             summary=card["summary"], tags=json.dumps(card["tags"], ensure_ascii=False))
    except llm.LLMUnavailable as e:
        _set(story_id, status="transcribed",
             error=f"Her words are saved. Gemma is offline, so no translation yet ({e}). Start Ollama and press 'Remember again'.")
    except Exception as e:  # noqa: BLE001
        log.exception("remember failed")
        _set(story_id, status="transcribed", error=f"Gemma step failed: {e}")


# ---------------------------------------------------------------- ask
KEYWORDS_SYS = (
    "Turn the question into search keywords for a transcript archive of a grandmother speaking Hindi/Awadhi. "
    'Return JSON {"keywords": [...]} with 4-10 keywords: English words AND their Hindi equivalents in Devanagari '
    "(include common spoken variants). Nouns only."
)

ANSWER_SYS = (
    "You are a careful family archivist. You are NOT {name} and you must never speak as her or invent her words. "
    "Answer the family's question using ONLY the numbered excerpts from {name}'s own recordings below. "
    "Write in the language of the question, in third person ('{name} said...'). "
    "Quote her actual words where it helps (original, then English in brackets). Cite excerpts like [1], [2]. "
    "If the excerpts do not answer the question, say plainly that she did not talk about this in the recordings, "
    "and suggest someone in the family could ask an elder and record the answer. Keep it under 120 words."
)


def ask(elder_id: int, question: str) -> dict:
    with db.tx() as con:
        elder = db.row(con.execute("SELECT * FROM elders WHERE id = ?", (elder_id,)).fetchone())
        segs = db.rows(con.execute(
            "SELECT g.story_id, g.idx, g.start, g.end, g.text, g.translation AS extra, s.title "
            "FROM segments g JOIN stories s ON s.id = g.story_id WHERE s.elder_id = ?", (elder_id,)))
    titles = {s["story_id"]: s["title"] for s in segs}
    query = question
    try:
        kw = llm.chat_json(KEYWORDS_SYS, question).get("keywords") or []
        query += " " + " ".join(str(k) for k in kw if isinstance(k, (str, int)))
    except llm.LLMUnavailable:
        pass
    hits = search.bm25(query, search.passages(segs), k=5)
    sources = [{"n": i + 1, "story_id": h["story_id"], "title": titles.get(h["story_id"]) or "Untitled story",
                "start": h["start"], "end": h["end"], "text": h["text"], "translation": h["extra"].strip()}
               for i, h in enumerate(hits)]
    if not sources:
        return {"answer": f"{elder['name']} didn't talk about this in any recording yet. "
                          "Maybe someone in the family remembers. Ask them, and record the answer here.",
                "sources": [], "grounded": False}
    excerpts = "\n\n".join(f"[{s['n']}] ({s['title']}) {s['text']}\n    English: {s['translation']}" for s in sources)
    try:
        answer = llm.chat(ANSWER_SYS.format(name=elder["name"]), f"EXCERPTS:\n{excerpts}\n\nQUESTION: {question}")
    except llm.LLMUnavailable:
        answer = "Gemma is offline, so here are the closest moments from her recordings. Press play to hear her."
    return {"answer": answer, "sources": sources, "grounded": True}
