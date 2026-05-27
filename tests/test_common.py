import sqlite3
from pathlib import Path

from scripts._common import RawPageRecord, init_sqlite, read_jsonl, write_jsonl


def test_raw_page_record_accepts_required_fields():
    record = RawPageRecord(
        url="https://example.com/product",
        final_url="https://example.com/product",
        status_code=200,
        fetch_method="httpx",
        html="<html>hello</html>",
        markdown="# Hello",
        content_quality_score=0.86,
        error_type=None,
        error_message=None,
        collected_at="2026-05-15T00:00:00Z",
    )

    assert record.fetch_method == "httpx"
    assert record.content_quality_score == 0.86


def test_jsonl_round_trip(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    records = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]

    write_jsonl(path, records)

    assert read_jsonl(path) == records
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_init_sqlite_creates_expected_tables(tmp_path: Path):
    path = tmp_path / "geo_benchmark.sqlite"

    init_sqlite(path)

    with sqlite3.connect(path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert {
        "runs",
        "documents",
        "chunks",
        "retrieval_results",
        "generation_results",
    }.issubset(tables)
