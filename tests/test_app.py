import importlib
import io
import time
import zipfile

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DVA_DATA_DIR", str(tmp_path))
    from app import config
    importlib.reload(config)
    from app import db, pipeline, main
    importlib.reload(db); importlib.reload(pipeline); importlib.reload(main)
    from tests import fakes
    fakes.install(monkeypatch)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def wait_done(c, sid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(f"/api/stories/{sid}").json()
        if st["status"] in ("done", "transcribed", "error"):
            return st
        time.sleep(0.05)
    raise AssertionError("story never finished")


def add_story(c, eid):
    audio = io.BytesIO(b"\x1aE\xdf\xa3" + b"0" * 4000)
    r = c.post(f"/api/elders/{eid}/stories", files={"audio": ("story.webm", audio, "audio/webm")}, data={"language": "hi"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_full_flow(client):
    eid = client.post("/api/elders", json={"name": "Dadi", "relation": "Father's mother"}).json()["id"]
    st = wait_done(client, add_story(client, eid))
    assert st["status"] == "done"
    assert st["title"] == "Thekua on Diwali Night"
    assert len(st["segments"]) == 5
    assert st["segments"][0]["translation"].startswith("When we were little")
    assert "thekua" in st["tags"]["foods"]
    assert st["tags"]["keepsake"].startswith("दीया")

    elders = client.get("/api/elders").json()
    assert elders[0]["story_count"] == 1 and elders[0]["seconds"] == 31.0

    ans = client.post(f"/api/elders/{eid}/ask", json={"question": "What did she cook for Diwali?"}).json()
    assert ans["grounded"] and ans["sources"]
    assert "ठेकुआ" in ans["sources"][0]["text"]
    assert ans["sources"][0]["start"] == 0.0

    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export").content))
    names = z.namelist()
    assert "memory-book/index.html" in names and any(n.startswith("memory-book/audio/") for n in names)
    page = z.read("memory-book/index.html").decode()
    assert "Thekua on Diwali Night" in page and "ठेकुआ" in page


def test_ask_never_invents(client):
    eid2 = client.post("/api/elders", json={"name": "Nanaji"}).json()["id"]
    ans = client.post(f"/api/elders/{eid2}/ask", json={"question": "What was his first job?"}).json()
    assert ans["sources"] == [] and not ans["grounded"]
    assert "didn't talk about this" in ans["answer"]


def test_gemma_offline_keeps_her_words(client, monkeypatch):
    from app import llm

    def down(*a, **k):
        raise llm.LLMUnavailable("connection refused")
    monkeypatch.setattr(llm, "chat_json", down)
    monkeypatch.setattr(llm, "chat", down)
    eid = client.post("/api/elders", json={"name": "Dadi"}).json()["id"]
    st = wait_done(client, add_story(client, eid))
    assert st["status"] == "transcribed"
    assert len(st["segments"]) == 5 and "Her words are saved" in st["error"]
    # Ask still works and returns her own voice clips without Gemma
    ans = client.post(f"/api/elders/{eid}/ask", json={"question": "दिवाली ठेकुआ"}).json()
    assert ans["sources"] and "Gemma is offline" in ans["answer"]


def test_validation(client):
    assert client.post("/api/elders", json={"name": "  "}).status_code == 400
    eid = client.post("/api/elders", json={"name": "Dadi"}).json()["id"]
    r = client.post(f"/api/elders/{eid}/stories", files={"audio": ("x.exe", io.BytesIO(b"0" * 5000), "x")})
    assert r.status_code == 400
    r = client.post(f"/api/elders/{eid}/stories", files={"audio": ("x.webm", io.BytesIO(b"0"), "audio/webm")})
    assert r.status_code == 400
    assert client.get("/api/elders/999").status_code == 404


def test_model_autopick(monkeypatch):
    from app import llm, config
    importlib.reload(llm)
    monkeypatch.setattr(config, "OLLAMA_MODEL", "")

    class R:
        def raise_for_status(self): pass
        def json(self): return {"models": [{"name": "llama3.2:3b"}, {"name": "embeddinggemma:latest"}, {"name": "gemma3:4b"}]}
    monkeypatch.setattr(llm.httpx, "get", lambda *a, **k: R())
    assert llm.model_name() == "gemma3:4b"


def test_bm25_cross_language():
    from app import search
    segs = [{"story_id": 1, "idx": i, "start": i, "end": i + 1, "text": t, "extra": e}
            for i, (t, e) in enumerate([("गाँव में बारिश", "rain in the village"), ("ठेकुआ बनाती थीं", "she made thekua"),
                                        ("शादी के गीत", "wedding songs")])]
    hits = search.bm25("wedding songs", search.passages(segs, window=1))
    assert hits[0]["text"] == "शादी के गीत"
