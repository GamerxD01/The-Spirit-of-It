import logging
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, llm, pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
STATIC = Path(__file__).parent / "static"
AUDIO_EXT = {".webm", ".ogg", ".mp3", ".m4a", ".wav", ".flac", ".aac", ".opus", ".mp4"}

# One worker: Whisper + Gemma on a laptop should take turns, not fight for RAM.
worker = ThreadPoolExecutor(max_workers=1)
config.ensure_dirs()


@asynccontextmanager
async def lifespan(_app):
    db.init()
    with db.tx() as con:  # resume anything interrupted by a closed laptop lid
        pending = con.execute("SELECT id FROM stories WHERE status IN ('queued','transcribing','remembering')").fetchall()
    for r in pending:
        worker.submit(pipeline.process, r["id"])
    yield


app = FastAPI(title="Dadi's Voice Archive", lifespan=lifespan)
app.mount("/audio", StaticFiles(directory=config.AUDIO_DIR), name="audio")


# ------------------------------------------------------------------ status
@app.get("/api/status")
def status():
    out = {"whisper": config.WHISPER_MODEL, "ollama": config.OLLAMA_URL, "model": None, "llm_ok": False, "error": ""}
    try:
        out["model"] = llm.model_name()
        out["llm_ok"] = True
    except llm.LLMUnavailable as e:
        out["error"] = str(e)
    return out


# ------------------------------------------------------------------ elders
class ElderIn(BaseModel):
    name: str
    relation: str = ""
    years: str = ""
    note: str = ""


@app.get("/api/elders")
def list_elders():
    with db.tx() as con:
        return db.rows(con.execute(
            "SELECT e.*, (SELECT COUNT(*) FROM stories s WHERE s.elder_id = e.id) AS story_count, "
            "(SELECT COALESCE(SUM(duration),0) FROM stories s WHERE s.elder_id = e.id) AS seconds "
            "FROM elders e ORDER BY e.id"))


@app.post("/api/elders")
def create_elder(e: ElderIn):
    if not e.name.strip():
        raise HTTPException(400, "Name is required")
    with db.tx() as con:
        cur = con.execute("INSERT INTO elders (name, relation, years, note) VALUES (?,?,?,?)",
                          (e.name.strip(), e.relation.strip(), e.years.strip(), e.note.strip()))
        return {"id": cur.lastrowid}


@app.get("/api/elders/{elder_id}")
def get_elder(elder_id: int):
    with db.tx() as con:
        el = db.row(con.execute("SELECT * FROM elders WHERE id = ?", (elder_id,)).fetchone())
        if not el:
            raise HTTPException(404, "Not found")
        el["stories"] = db.rows(con.execute(
            "SELECT id, title, summary, status, error, duration, language, tags, created_at FROM stories "
            "WHERE elder_id = ? ORDER BY id DESC", (elder_id,)))
    return el


@app.delete("/api/elders/{elder_id}")
def delete_elder(elder_id: int):
    with db.tx() as con:
        files = [r["audio_file"] for r in con.execute("SELECT audio_file FROM stories WHERE elder_id = ?", (elder_id,))]
        con.execute("DELETE FROM elders WHERE id = ?", (elder_id,))
    for f in files:
        (config.AUDIO_DIR / f).unlink(missing_ok=True)
    return {"ok": True}


# ------------------------------------------------------------------ stories
@app.post("/api/elders/{elder_id}/stories")
async def add_story(elder_id: int, audio: UploadFile = File(...), language: str = Form("")):
    ext = Path(audio.filename or "").suffix.lower() or ".webm"
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"Unsupported audio type {ext}")
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM elders WHERE id = ?", (elder_id,)).fetchone():
            raise HTTPException(404, "Elder not found")
    name = f"{uuid.uuid4().hex}{ext}"
    data = await audio.read()
    if len(data) < 1000:
        raise HTTPException(400, "That recording is empty")
    (config.AUDIO_DIR / name).write_bytes(data)
    with db.tx() as con:
        sid = con.execute("INSERT INTO stories (elder_id, audio_file, status) VALUES (?,?, 'queued')",
                          (elder_id, name)).lastrowid
    worker.submit(pipeline.process, sid, language or None)
    return {"id": sid}


@app.get("/api/stories/{story_id}")
def get_story(story_id: int):
    with db.tx() as con:
        st = db.row(con.execute("SELECT s.*, e.name AS elder_name FROM stories s JOIN elders e ON e.id = s.elder_id "
                                "WHERE s.id = ?", (story_id,)).fetchone())
        if not st:
            raise HTTPException(404, "Not found")
        st["segments"] = db.rows(con.execute(
            "SELECT idx, start, end, text, translation FROM segments WHERE story_id = ? ORDER BY idx", (story_id,)))
    return st


class StoryPatch(BaseModel):
    title: str


@app.patch("/api/stories/{story_id}")
def patch_story(story_id: int, p: StoryPatch):
    with db.tx() as con:
        con.execute("UPDATE stories SET title = ? WHERE id = ?", (p.title.strip(), story_id))
    return {"ok": True}


@app.post("/api/stories/{story_id}/remember")
def re_remember(story_id: int):
    st = get_story(story_id)
    if not st["segments"]:
        worker.submit(pipeline.process, story_id)
    else:
        worker.submit(pipeline.remember, story_id, st["elder_name"])
    return {"ok": True}


@app.delete("/api/stories/{story_id}")
def delete_story(story_id: int):
    with db.tx() as con:
        r = con.execute("SELECT audio_file FROM stories WHERE id = ?", (story_id,)).fetchone()
        con.execute("DELETE FROM stories WHERE id = ?", (story_id,))
    if r:
        (config.AUDIO_DIR / r["audio_file"]).unlink(missing_ok=True)
    return {"ok": True}


# ------------------------------------------------------------------ ask + export
class AskIn(BaseModel):
    question: str


@app.post("/api/elders/{elder_id}/ask")
def ask(elder_id: int, q: AskIn):
    if not q.question.strip():
        raise HTTPException(400, "Ask something")
    get_elder(elder_id)
    return pipeline.ask(elder_id, q.question.strip())


@app.get("/api/export")
def export():
    from .export import build_zip
    return Response(build_zip(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=family-memory-book.zip"})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
