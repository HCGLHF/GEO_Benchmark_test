from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path
from typing import Any

from scripts._common import stable_id
from scripts.eval_retrieval import calculate_retrieval_metrics, insert_sqlite, keyword_search, reciprocal_rank_fusion
from scripts.geo_eval.io import read_csv, safe_json_list


COMPACT_RETRIEVAL_FIELDS = [
    "run_id",
    "query_id",
    "query",
    "top_k",
    "own_brand_rank",
    "own_brand_in_top_3",
    "own_brand_in_top_5",
    "own_brand_in_top_10",
    "winning_brand",
    "winning_source_type",
    "competitor_above_owned",
    "matched_urls_json",
]


def compact_retrieval_row(record: Any) -> dict[str, Any]:
    data = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    return {field: data.get(field) for field in COMPACT_RETRIEVAL_FIELDS}


def evidence_row(record: Any, text_preview_chars: int = 500) -> dict[str, Any]:
    data = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    chunks = safe_json_list(data.get("retrieved_chunks_json", "[]"))
    compact_chunks = []
    for chunk in chunks:
        compact_chunks.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "url": chunk.get("url"),
                "brand": chunk.get("brand"),
                "title": chunk.get("title"),
                "keyword_score": chunk.get("keyword_score"),
                "rrf_score": chunk.get("rrf_score"),
                "text_preview": str(chunk.get("text", ""))[:text_preview_chars],
            }
        )
    return {
        "query_id": data.get("query_id"),
        "query": data.get("query"),
        "matched_urls": safe_json_list(data.get("matched_urls_json", "[]")),
        "retrieved_chunks": compact_chunks,
    }


def write_retrieval_outputs(csv_path: Path, evidence_path: Path, records: list[Any]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPACT_RETRIEVAL_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(compact_retrieval_row(record))

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(evidence_row(record), ensure_ascii=False) + "\n")


def evaluate_retrieval(config: dict[str, Any], queries_csv: Path, output_csv: Path) -> list[dict[str, str]]:
    retrieval_config = config.get("retrieval", {})
    with Path(retrieval_config.get("keyword_index", "data/processed/bm25_index.pkl")).open("rb") as handle:
        artifact = pickle.load(handle)
    top_k = int(config.get("run", {}).get("top_k", 10))
    run_id = stable_id("run", f"geo-evaluator:{queries_csv.stat().st_mtime}:{top_k}")
    records = []
    for query in read_csv(queries_csv):
        keyword_results = keyword_search(query["query"], artifact, top_k)
        combined = reciprocal_rank_fusion([keyword_results])[:top_k]
        records.append(
            calculate_retrieval_metrics(
                query_id=query["query_id"],
                query=query["query"],
                target_brand=query.get("target_brand", ""),
                results=combined,
                top_k=top_k,
                run_id=run_id,
            )
        )
    write_retrieval_outputs(output_csv, output_csv.with_name("retrieval_evidence.jsonl"), records)
    sqlite_path = retrieval_config.get("sqlite")
    if sqlite_path:
        insert_sqlite(Path(sqlite_path), records)
    return read_csv(output_csv)


def is_true(value: Any) -> bool:
    return str(value).lower() == "true"


def retrieval_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    query_count = len(rows)
    recall_hits = sum(is_true(row.get("own_brand_in_top_5")) for row in rows)
    competitor_wins = sum(is_true(row.get("competitor_above_owned")) for row in rows)
    ranked = [int(row["own_brand_rank"]) for row in rows if str(row.get("own_brand_rank", "")).isdigit()]
    return {
        "query_count": query_count,
        "recall_at_5": recall_hits / query_count if query_count else 0.0,
        "competitor_win_rate": competitor_wins / query_count if query_count else 0.0,
        "average_own_brand_rank": sum(ranked) / len(ranked) if ranked else None,
        "own_brand_ranked_count": len(ranked),
    }


def insert_retrieval_sqlite(path: Path, records: list[Any]) -> None:
    insert_sqlite(path, records)
