from __future__ import annotations

import hashlib
import json
import sqlite3
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field


FETCH_METHODS = {
    "httpx",
    "playwright",
    "firecrawl",
    "scrapingbee",
    "zyte",
    "bright_data",
    "apify",
    "browserless",
}

ERROR_TYPES = {
    "blocked",
    "captcha",
    "timeout",
    "http_error",
    "empty_content",
    "low_quality_content",
    "parse_error",
    "unknown",
}


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawPageRecord(StrictRecord):
    url: str
    final_url: str
    status_code: int | None
    fetch_method: str
    html: str
    markdown: str
    content_quality_score: float = Field(ge=0.0, le=1.0)
    error_type: str | None = None
    error_message: str | None = None
    collected_at: str


class FetchAttemptRecord(StrictRecord):
    url: str
    fetch_method: str
    status_code: int | None = None
    content_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    error_type: str | None = None
    error_message: str | None = None
    attempted_at: str


class DocumentRecord(StrictRecord):
    document_id: str
    url: str
    site: str
    brand: str
    title: str
    description: str | None = None
    content: str
    source_type: str
    page_type: str = "unknown"
    collected_at: str
    content_hash: str | None = None


class ChunkRecord(StrictRecord):
    chunk_id: str
    document_id: str
    url: str
    brand: str
    title: str
    heading: str | None = None
    text: str
    source_type: str
    page_type: str = "unknown"
    token_count: int
    content_hash: str | None = None


class QueryRecord(StrictRecord):
    query_id: str
    query: str
    intent: str | None = None
    priority: str | None = None
    target_brand: str
    notes: str | None = None
    expected_owned_urls: str | None = None


class RetrievalResultRecord(StrictRecord):
    run_id: str
    query_id: str
    query: str
    top_k: int
    own_brand_rank: int | None = None
    own_brand_in_top_3: bool
    own_brand_in_top_5: bool
    own_brand_in_top_10: bool
    winning_brand: str | None = None
    winning_source_type: str | None = None
    competitor_above_owned: bool
    matched_urls_json: str
    retrieved_chunks_json: str


class GenerationResultRecord(StrictRecord):
    run_id: str
    query_id: str
    provider: str
    model_name: str
    mode: Literal["direct", "grounded"]
    repeat_index: int = 0
    temperature: float = 0.0
    prompt_version: str = "v1"
    context_top_k: int = 10
    raw_answer: str
    brand_mentioned: bool
    cited_own_url: bool
    recommended_own_brand: bool
    competitors_mentioned_json: str
    citations_json: str
    answer_coverage_score: int = Field(ge=0, le=3)
    unsupported_claims_json: str = "[]"
    latency_ms: int | None = None
    cost_estimate: float | None = None


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _to_dict(record: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(record, BaseModel):
        return record.model_dump(mode="json")
    return record


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_jsonl(path: Path, records: Iterable[BaseModel | dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_to_dict(record), ensure_ascii=False) + "\n")


def write_jsonl(path: Path, records: Iterable[BaseModel | dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_to_dict(record), ensure_ascii=False) + "\n")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def init_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              run_type TEXT NOT NULL,
              corpus_version TEXT,
              query_set_version TEXT,
              retriever_type TEXT,
              embedding_model TEXT,
              chunk_strategy TEXT,
              top_k INTEGER,
              notes TEXT
            );

            CREATE TABLE IF NOT EXISTS queries (
              query_id TEXT PRIMARY KEY,
              query TEXT NOT NULL,
              intent TEXT,
              priority TEXT,
              target_brand TEXT,
              expected_owned_urls TEXT,
              notes TEXT
            );

            CREATE TABLE IF NOT EXISTS documents (
              document_id TEXT PRIMARY KEY,
              url TEXT NOT NULL,
              site TEXT,
              brand TEXT,
              source_type TEXT,
              page_type TEXT,
              title TEXT,
              description TEXT,
              collected_at TEXT,
              content_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS chunks (
              chunk_id TEXT PRIMARY KEY,
              document_id TEXT,
              url TEXT,
              brand TEXT,
              source_type TEXT,
              page_type TEXT,
              heading TEXT,
              text TEXT,
              token_count INTEGER,
              content_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS retrieval_results (
              run_id TEXT,
              query_id TEXT,
              top_k INTEGER,
              own_brand_rank INTEGER,
              own_brand_in_top_3 INTEGER,
              own_brand_in_top_5 INTEGER,
              own_brand_in_top_10 INTEGER,
              winning_brand TEXT,
              winning_source_type TEXT,
              competitor_above_owned INTEGER,
              matched_urls_json TEXT,
              retrieved_chunks_json TEXT
            );

            CREATE TABLE IF NOT EXISTS generation_results (
              run_id TEXT,
              query_id TEXT,
              provider TEXT,
              model_name TEXT,
              mode TEXT,
              repeat_index INTEGER,
              temperature REAL,
              prompt_version TEXT,
              context_top_k INTEGER,
              raw_answer TEXT,
              brand_mentioned INTEGER,
              cited_own_url INTEGER,
              recommended_own_brand INTEGER,
              competitors_mentioned_json TEXT,
              citations_json TEXT,
              answer_coverage_score INTEGER,
              unsupported_claims_json TEXT,
              latency_ms INTEGER,
              cost_estimate REAL
            );
            """
        )
