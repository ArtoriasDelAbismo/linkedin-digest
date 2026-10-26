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
        created_at DOUBLE PRECISION NOT NULL,
        kind TEXT NOT NULL DEFAULT 'digest',  -- digest | spotlight
        image_url TEXT,
        image_alt TEXT
    );
    CREATE TABLE IF NOT EXISTS auth (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        access_token TEXT NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL,
        person_urn TEXT NOT NULL,
        name TEXT
    );
"""
# Columns added after the first release, for databases created before them
NEW_COLUMNS = {"drafts": [("kind", "TEXT NOT NULL DEFAULT 'digest'"), ("image_url", "TEXT"), ("image_alt", "TEXT")]}
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
            _add_new_columns(cur)
            _schema_ready = True
        yield cur
        conn.commit()
    finally:
        conn.close()


def _add_new_columns(cur) -> None:
    for table, columns in NEW_COLUMNS.items():
        if PG_URL:
            for name, decl in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {decl}")
            continue
        cur.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in cur.fetchall()}
        for name, decl in columns:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


class _PgCursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        return self._cur.execute(sql.replace("?", "%s"), params)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


def new_draft(text: str, kind: str = "digest", image_url: str | None = None, image_alt: str | None = None) -> str:
    draft_id = secrets.token_urlsafe(16)  # doubles as the secret in the approval link
    with _cursor() as c:
        c.execute("INSERT INTO drafts (id, text, created_at, kind, image_url, image_alt) VALUES (?, ?, ?, ?, ?, ?)",
                  (draft_id, text, time.time(), kind, image_url, image_alt))
    return draft_id


def get_draft(draft_id: str):
    with _cursor() as c:
        c.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        return c.fetchone()


def recent_drafts(days: int) -> list:
    """Drafts from the last `days` days that were posted or are still waiting for review."""
    with _cursor() as c:
        c.execute("SELECT * FROM drafts WHERE created_at > ? AND status != 'skipped' ORDER BY created_at DESC",
                  (time.time() - days * 86400,))
        return c.fetchall()


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
