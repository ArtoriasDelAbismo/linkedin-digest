"""Storage for drafts and the LinkedIn token.

Uses Postgres when DATABASE_URL (or POSTGRES_URL) is set, e.g. on Vercel with Neon,
and a local SQLite file otherwise.
"""

import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

PG_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
DB_PATH = Path(os.getenv("DATA_DIR", ".")) / "digest.db"

SCHEMA = """
    CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY,
        text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',  -- pending | posted | skipped
        post_urn TEXT,
        created_at DOUBLE PRECISION NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        access_token TEXT NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL,
        person_urn TEXT NOT NULL,
        name TEXT
    );
"""
_schema_ready = False


@contextmanager
def _cursor():
    """Yield a cursor that takes '?' placeholders on either backend, and commit on exit."""
    global _schema_ready
    if PG_URL:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(PG_URL, row_factory=dict_row)
        cur = _PgCursor(conn.cursor())
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    try:
        if not _schema_ready:
            for stmt in filter(str.strip, SCHEMA.split(";")):
                cur.execute(stmt)
            _schema_ready = True
        yield cur
        conn.commit()
    finally:
        conn.close()


class _PgCursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        return self._cur.execute(sql.replace("?", "%s"), params)

    def fetchone(self):
        return self._cur.fetchone()


def new_draft(text: str) -> str:
    draft_id = secrets.token_urlsafe(16)  # doubles as the secret in the approval link
    with _cursor() as c:
        c.execute("INSERT INTO drafts (id, text, created_at) VALUES (?, ?, ?)", (draft_id, text, time.time()))
    return draft_id


def get_draft(draft_id: str):
    with _cursor() as c:
        c.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        return c.fetchone()


def update_draft(draft_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _cursor() as c:
        c.execute(f"UPDATE drafts SET {cols} WHERE id = ?", (*fields.values(), draft_id))


def save_auth(access_token: str, expires_at: float, person_urn: str, name: str) -> None:
    with _cursor() as c:
        c.execute("""
            INSERT INTO auth (id, access_token, expires_at, person_urn, name) VALUES (1, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET access_token = excluded.access_token,
                expires_at = excluded.expires_at, person_urn = excluded.person_urn, name = excluded.name
        """, (access_token, expires_at, person_urn, name))


def get_auth():
    with _cursor() as c:
        c.execute("SELECT * FROM auth WHERE id = 1")
        return c.fetchone()
