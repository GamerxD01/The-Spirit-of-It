import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS elders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    relation TEXT DEFAULT '',
    years TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    elder_id INTEGER NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
    audio_file TEXT NOT NULL,
    language TEXT DEFAULT '',
    duration REAL DEFAULT 0,
    status TEXT DEFAULT 'queued',      -- queued, transcribing, remembering, done, error
    error TEXT DEFAULT '',
    title TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    transcript TEXT DEFAULT '',
    translation TEXT DEFAULT '',
    tags TEXT DEFAULT '{}',            -- JSON: people, places, foods, songs, era
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL,
    translation TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS seg_story ON segments(story_id);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    config.ensure_dirs()
    with tx() as con:
        con.executescript(SCHEMA)


def row(r):
    if r is None:
        return None
    d = dict(r)
    if "tags" in d:
        try:
            d["tags"] = json.loads(d["tags"] or "{}")
        except json.JSONDecodeError:
            d["tags"] = {}
    return d


def rows(rs):
    return [row(r) for r in rs]
