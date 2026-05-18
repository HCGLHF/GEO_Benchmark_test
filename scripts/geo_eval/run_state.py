from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts._common import utc_now_iso


class RunState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_state (
                    task_type TEXT NOT NULL,
                    query_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_fingerprint TEXT NOT NULL DEFAULT 'default',
                    status TEXT NOT NULL,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_type, query_id, model, task_fingerprint)
                )
                """
            )

    def status(self, task_type: str, query_id: str, model: str, task_fingerprint: str = "default") -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM task_state WHERE task_type = ? AND query_id = ? AND model = ? AND task_fingerprint = ?",
                (task_type, query_id, model, task_fingerprint),
            ).fetchone()
        return row["status"] if row else "pending"

    def error(self, task_type: str, query_id: str, model: str, task_fingerprint: str = "default") -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT error FROM task_state WHERE task_type = ? AND query_id = ? AND model = ? AND task_fingerprint = ?",
                (task_type, query_id, model, task_fingerprint),
            ).fetchone()
        return row["error"] if row else None

    def mark_complete(self, task_type: str, query_id: str, model: str, task_fingerprint: str = "default") -> None:
        self._upsert(task_type, query_id, model, task_fingerprint, "complete", None)

    def mark_failed(self, task_type: str, query_id: str, model: str, error: str, task_fingerprint: str = "default") -> None:
        self._upsert(task_type, query_id, model, task_fingerprint, "failed", error)

    def _upsert(self, task_type: str, query_id: str, model: str, task_fingerprint: str, status: str, error: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_state (task_type, query_id, model, task_fingerprint, status, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_type, query_id, model, task_fingerprint)
                DO UPDATE SET status = excluded.status, error = excluded.error, updated_at = excluded.updated_at
                """,
                (task_type, query_id, model, task_fingerprint, status, error, utc_now_iso()),
            )
