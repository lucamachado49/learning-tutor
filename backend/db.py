"""
db.py — Persistência SQLite: sessões, mensagens e memória do aluno.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from threading import Lock

import config

_lock = Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'Nova Conversa',
                language   TEXT NOT NULL DEFAULT 'en',
                level      TEXT NOT NULL DEFAULT 'B1',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                feedback   TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mistakes (
                id         TEXT PRIMARY KEY,
                domain     TEXT NOT NULL,
                text       TEXT NOT NULL,
                norm       TEXT NOT NULL,
                count      INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen  TEXT NOT NULL,
                UNIQUE (domain, norm)
            );
        """)
        # Migração: sessões antigas usavam só "language"
        cols = _columns(conn, "sessions")
        if "domain" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN domain TEXT")
            conn.execute("UPDATE sessions SET domain = language")
        if "mode" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'conversation'")
        conn.commit()


# --- Sessões ---------------------------------------------------------------
def list_sessions(limit: int = 100) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def create_session(domain: str, level: str, mode: str) -> dict:
    now = now_iso()
    sid = str(uuid.uuid4())
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, language, domain, level, mode, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (sid, "Nova Conversa", domain, domain, level, mode, now, now),
        )
        conn.commit()
    return get_session(sid)  # type: ignore[return-value]


def update_session(session_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as conn:
        conn.execute(f"UPDATE sessions SET {sets} WHERE id=?", (*fields.values(), session_id))
        conn.commit()


def delete_session(session_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()


# --- Mensagens -------------------------------------------------------------
def get_messages(session_id: str, limit: int | None = None) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC", (session_id,)
        ).fetchall()
    msgs = [dict(r) for r in rows]
    return msgs[-limit:] if limit else msgs


def add_message(session_id: str, role: str, content: str, feedback: str = "") -> str:
    mid = str(uuid.uuid4())
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, feedback, created_at) VALUES (?,?,?,?,?,?)",
            (mid, session_id, role, content, feedback, now_iso()),
        )
        conn.commit()
    return mid


# --- Memória do aluno ------------------------------------------------------
def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def record_mistakes(domain: str, items: list[str]) -> None:
    now = now_iso()
    with _lock, _conn() as conn:
        for text in items:
            conn.execute(
                "INSERT INTO mistakes (id, domain, text, norm, first_seen, last_seen) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(domain, norm) DO UPDATE SET count = count + 1, last_seen = excluded.last_seen",
                (str(uuid.uuid4()), domain, text, _normalize(text), now, now),
            )
        conn.commit()


def top_mistakes(domain: str, limit: int = 10) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mistakes WHERE domain=? ORDER BY count DESC, last_seen DESC LIMIT ?",
            (domain, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_mistake(mistake_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM mistakes WHERE id=?", (mistake_id,))
        conn.commit()
