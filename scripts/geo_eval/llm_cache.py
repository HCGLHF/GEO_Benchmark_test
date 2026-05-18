from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from scripts._common import utc_now_iso


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_key_for_call(
    provider: str,
    model: str,
    task_type: str,
    prompt: str,
    input_hash: str,
    config_hash: str,
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "task_type": task_type,
            "prompt_hash": stable_hash(prompt),
            "input_hash": input_hash,
            "config_hash": config_hash,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return "llmcache_" + stable_hash(payload)[:24]


class LLMCache:
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
                CREATE TABLE IF NOT EXISTS llm_calls (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM llm_calls WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["response_json"])

    def put(
        self,
        key: str,
        provider: str,
        model: str,
        task_type: str,
        prompt_hash: str,
        input_hash: str,
        config_hash: str,
        response: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO llm_calls (
                    cache_key, provider, model, task_type, prompt_hash, input_hash,
                    config_hash, response_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    provider,
                    model,
                    task_type,
                    prompt_hash,
                    input_hash,
                    config_hash,
                    json.dumps(response, ensure_ascii=False, sort_keys=True),
                    utc_now_iso(),
                ),
            )
