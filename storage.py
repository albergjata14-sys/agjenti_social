"""Ruajtja e përhershme e bisedave në një databazë SQLite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("AGJENTI_DB_PATH", Path(__file__).parent / "data" / "chat_history.db"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent      TEXT NOT NULL,
            role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages(agent, id)")
    return conn


def load_messages(agent: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE agent = ? ORDER BY id",
            (agent,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_message(agent: str, role: str, content: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO messages (agent, role, content, created_at) VALUES (?, ?, ?, ?)",
            (agent, role, content, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def clear_messages(agent: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM messages WHERE agent = ?", (agent,))


def count_messages() -> dict[str, int]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT agent, COUNT(*) AS n FROM messages GROUP BY agent").fetchall()
    return {row["agent"]: row["n"] for row in rows}
