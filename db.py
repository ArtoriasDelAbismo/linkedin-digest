"""SQLite storage for drafts and the LinkedIn token."""

import os
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("DATA_DIR", ".")) / "digest.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending | posted | skipped
            post_urn TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            expires_at REAL NOT NULL,
            person_urn TEXT NOT NULL,
            name TEXT
        );
    """)
    return conn


def new_draft(text: str) -> str:
    draft_id = secrets.token_urlsafe(16)  # doubles as the secret in the approval link
    with _conn() as c:
        c.execute("INSERT INTO drafts (id, text, created_at) VALUES (?, ?, ?)", (draft_id, text, time.time()))
    return draft_id


def get_draft(draft_id: str) -> sqlite3.Row | None:
    with _conn() as c:
        return c.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()


def update_draft(draft_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE drafts SET {cols} WHERE id = ?", (*fields.values(), draft_id))


def save_auth(access_token: str, expires_at: float, person_urn: str, name: str) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO auth VALUES (1, ?, ?, ?, ?)", (access_token, expires_at, person_urn, name))


def get_auth() -> sqlite3.Row | None:
    with _conn() as c:
        return c.execute("SELECT * FROM auth WHERE id = 1").fetchone()
