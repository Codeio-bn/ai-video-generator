"""SQLite storage using the Python standard library only.

A fresh short-lived connection is opened per operation (WAL mode) so the API
request threads and the background render/job threads never share a connection.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scp_number TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT 'CC BY-SA 3.0',
    language TEXT NOT NULL DEFAULT 'en',
    style_bible TEXT NOT NULL DEFAULT '',
    narrator_voice TEXT NOT NULL DEFAULT '',
    target_episode_length INTEGER NOT NULL DEFAULT 30,
    source_text TEXT NOT NULL DEFAULT '',
    monthly_budget_cap REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS character_sheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL DEFAULT '',
    hook TEXT NOT NULL DEFAULT '',
    previously TEXT NOT NULL DEFAULT '',
    narration_script TEXT NOT NULL DEFAULT '',
    cliffhanger TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    narration_audio_path TEXT,
    narration_words TEXT,              -- JSON array of {word,start,end}
    music_path TEXT,
    last_render_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 0,
    narration_excerpt TEXT NOT NULL DEFAULT '',
    duration REAL NOT NULL DEFAULT 5.0,
    shot_type TEXT NOT NULL DEFAULT 'still_image',
    prompt TEXT NOT NULL DEFAULT '',
    camera_motion TEXT NOT NULL DEFAULT '',
    audio_description TEXT NOT NULL DEFAULT '',
    text_content TEXT NOT NULL DEFAULT '',
    kenburns_direction TEXT NOT NULL DEFAULT 'in',
    asset_path TEXT,
    takes TEXT,                        -- JSON array of asset paths
    selected_take INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'empty',
    cost REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS render_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER REFERENCES episodes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'render',
    status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|error
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    output_path TEXT,
    error TEXT,
    options TEXT,                      -- JSON of the render options used
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    episode_id INTEGER,
    shot_id INTEGER,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]
