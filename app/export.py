"""Export the archive as a plain HTML memory book + audio files in a zip.
No app, no server, no account needed to open it in 30 years. Just a browser."""
import html
import io
import zipfile

from . import config, db

CSS = """
body{margin:0;background:#1a0f0a;color:#f6e7d0;font:17px/1.6 Georgia,'Noto Serif Devanagari',serif}
main{max-width:760px;margin:0 auto;padding:32px 18px}
h1{color:#f5a524;font-weight:normal;font-size:2.2em;margin:0 0 4px}
h2{color:#f5a524;font-weight:normal;border-bottom:1px solid #5a3a22;padding-bottom:6px;margin-top:48px}
h3{margin:28px 0 4px}
.meta{color:#c9a98a;font-size:.9em}
blockquote{border-left:3px solid #f5a524;margin:12px 0;padding:4px 14px;font-style:italic;font-size:1.1em}
.line{margin:6px 0}.en{color:#c9a98a;display:block;font-size:.92em}
audio{width:100%;margin:8px 0}
.tags span{display:inline-block;border:1px solid #5a3a22;border-radius:12px;padding:0 10px;margin:2px;font-size:.85em}
footer{margin-top:60px;color:#8a6d55;font-size:.85em;text-align:center}
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def build_zip() -> bytes:
    with db.tx() as con:
        elders = db.rows(con.execute("SELECT * FROM elders ORDER BY id"))
        stories = db.rows(con.execute("SELECT * FROM stories ORDER BY elder_id, id"))
        segs = db.rows(con.execute("SELECT * FROM segments ORDER BY story_id, idx"))
    by_story: dict[int, list] = {}
    for g in segs:
        by_story.setdefault(g["story_id"], []).append(g)

    parts = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Our Family Memory Book</title><style>{CSS}</style></head><body><main>"
             "<h1>🪔 Our Family Memory Book</h1><p class='meta'>Recorded and kept at home. Their voices, in their words.</p>"]
    files = []
    for el in elders:
        parts.append(f"<h2>{_e(el['name'])}</h2><p class='meta'>{_e(el['relation'])} {_e(el['years'])}</p>")
        if el["note"]:
            parts.append(f"<p>{_e(el['note'])}</p>")
        for st in (s for s in stories if s["elder_id"] == el["id"] and s["status"] in ("done", "transcribed")):
            t = st["tags"] or {}
            parts.append(f"<h3>{_e(st['title'] or 'Untitled story')}</h3>")
            parts.append(f"<p class='meta'>{_e(t.get('era'))} · recorded {_e(st['created_at'][:10])}</p>")
            parts.append(f"<audio controls preload='none' src='audio/{_e(st['audio_file'])}'></audio>")
            files.append(st["audio_file"])
            if st["summary"]:
                parts.append(f"<p>{_e(st['summary'])}</p>")
            if t.get("keepsake"):
                parts.append(f"<blockquote>“{_e(t['keepsake'])}”</blockquote>")
            chips = [x for k in ("people", "places", "foods", "songs") for x in t.get(k, [])]
            if chips:
                parts.append("<p class='tags'>" + "".join(f"<span>{_e(c)}</span>" for c in chips) + "</p>")
            parts.append("<details><summary>Her words</summary>")
            for g in by_story.get(st["id"], []):
                en = f"<span class='en'>{_e(g['translation'])}</span>" if g["translation"] else ""
                parts.append(f"<p class='line'>{_e(g['text'])}{en}</p>")
            parts.append("</details>")
    parts.append("<footer>Made with Dadi's Voice Archive: Whisper + Gemma, running on our own computer.</footer></main></body></html>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("memory-book/index.html", "".join(parts))
        for f in files:
            p = config.AUDIO_DIR / f
            if p.exists():
                z.write(p, f"memory-book/audio/{f}")
    return buf.getvalue()
