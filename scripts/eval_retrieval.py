from __future__ import annotations

import argparse
import csv
import json
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import RetrievalResultRecord, init_sqlite, stable_id, write_jsonl
from scripts.build_keyword_index import tokenize


def reciprocal_rank_fusion(result_lists: list[list[dict[str, Any]]], k: int = 60) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            items[chunk_id] = item
    return [items[key] | {"rrf_score": score} for key, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)]


def keyword_search(query: str, artifact: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    query_terms = set(tokenize(query))
    scored = []
    for chunk, tokens in zip(artifact.get("chunks", []), artifact.get("tokenized", [])):
        score = sum(1 for token in tokens if token in query_terms)
        if score:
            scored.append(chunk | {"keyword_score": score})
    return sorted(scored, key=lambda item: item["keyword_score"], reverse=True)[:top_k]


def calculate_retrieval_metrics(
    query_id: str,
    query: str,
    target_brand: str,
    results: list[dict[str, Any]],
    top_k: int,
    run_id: str = "run_test",
) -> RetrievalResultRecord:
    own_rank = None
    for rank, result in enumerate(results[:top_k], start=1):
        if result.get("brand") == target_brand:
            own_rank = rank
            break

    competitor_above = False
    if own_rank is None:
        competitor_above = any(result.get("brand") and result.get("brand") != target_brand for result in results[:top_k])
    else:
        competitor_above = any(
            result.get("brand") and result.get("brand") != target_brand
            for result in results[: own_rank - 1]
        )

    winner = results[0] if results else {}
    return RetrievalResultRecord(
        run_id=run_id,
        query_id=query_id,
        query=query,
        top_k=top_k,
        own_brand_rank=own_rank,
        own_brand_in_top_3=own_rank is not None and own_rank <= 3,
        own_brand_in_top_5=own_rank is not None and own_rank <= 5,
        own_brand_in_top_10=own_rank is not None and own_rank <= 10,
        winning_brand=winner.get("brand"),
        winning_source_type=winner.get("source_type"),
        competitor_above_owned=competitor_above,
        matched_urls_json=json.dumps([item.get("url") for item in results[:top_k]]),
        retrieved_chunks_json=json.dumps(results[:top_k]),
    )


COMPACT_RESULT_FIELDS = [
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


def compact_result_row(record: RetrievalResultRecord) -> dict[str, Any]:
    data = record.model_dump()
    return {field: data.get(field) for field in COMPACT_RESULT_FIELDS}


def evidence_result_row(record: RetrievalResultRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "query_id": record.query_id,
        "query": record.query,
        "top_k": record.top_k,
        "matched_urls_json": record.matched_urls_json,
        "retrieved_chunks_json": record.retrieved_chunks_json,
    }


def load_queries(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def default_evidence_path(path: Path) -> Path:
    return path.with_name("retrieval_evidence.jsonl")


def write_results(path: Path, records: list[RetrievalResultRecord], evidence_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPACT_RESULT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(compact_result_row(record))

    evidence_path = evidence_path or default_evidence_path(path)
    write_jsonl(evidence_path, [evidence_result_row(record) for record in records])


def insert_sqlite(path: Path, records: list[RetrievalResultRecord]) -> None:
    init_sqlite(path)
    with sqlite3.connect(path) as conn:
        for record in records:
            data = record.model_dump()
            conn.execute(
                """
                INSERT INTO retrieval_results (
                  run_id, query_id, top_k, own_brand_rank, own_brand_in_top_3,
                  own_brand_in_top_5, own_brand_in_top_10, winning_brand,
                  winning_source_type, competitor_above_owned, matched_urls_json,
                  retrieved_chunks_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["run_id"],
                    data["query_id"],
                    data["top_k"],
                    data["own_brand_rank"],
                    int(data["own_brand_in_top_3"]),
                    int(data["own_brand_in_top_5"]),
                    int(data["own_brand_in_top_10"]),
                    data["winning_brand"],
                    data["winning_source_type"],
                    int(data["competitor_above_owned"]),
                    data["matched_urls_json"],
                    data["retrieved_chunks_json"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval metrics.")
    parser.add_argument("--queries", default="data/eval/queries.csv")
    parser.add_argument("--keyword-index", default="data/processed/bm25_index.pkl")
    parser.add_argument("--output", default="data/eval/retrieval_results.csv")
    parser.add_argument("--evidence-output", default=None)
    parser.add_argument("--sqlite", default="data/geo_benchmark.sqlite")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    with Path(args.keyword_index).open("rb") as handle:
        artifact = pickle.load(handle)

    run_id = stable_id("run", f"retrieval:{Path(args.queries).stat().st_mtime}")
    records = []
    for query in load_queries(Path(args.queries)):
        keyword_results = keyword_search(query["query"], artifact, args.top_k)
        combined = reciprocal_rank_fusion([keyword_results])[: args.top_k]
        records.append(
            calculate_retrieval_metrics(
                query_id=query["query_id"],
                query=query["query"],
                target_brand=query.get("target_brand", ""),
                results=combined,
                top_k=args.top_k,
                run_id=run_id,
            )
        )

    write_results(Path(args.output), records, Path(args.evidence_output) if args.evidence_output else None)
    insert_sqlite(Path(args.sqlite), records)
    print(f"Wrote retrieval results for {len(records)} queries to {args.output}")


if __name__ == "__main__":
    main()
