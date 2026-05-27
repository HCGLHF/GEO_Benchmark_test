import csv
import json
from pathlib import Path

from scripts.eval_generation import load_retrieval_evidence


def test_load_retrieval_evidence_prefers_jsonl_when_csv_is_compact(tmp_path: Path):
    csv_path = tmp_path / "retrieval_results.csv"
    evidence_path = tmp_path / "retrieval_evidence.jsonl"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query_id", "matched_urls_json"])
        writer.writeheader()
        writer.writerow({"query_id": "q1", "matched_urls_json": '["https://own.example"]'})
    evidence_path.write_text(
        json.dumps(
            {
                "query_id": "q1",
                "retrieved_chunks_json": json.dumps(
                    [{"url": "https://own.example", "brand": "Own", "text": "Useful content"}]
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = load_retrieval_evidence(csv_path)

    assert evidence["q1"][0]["url"] == "https://own.example"


def test_load_retrieval_evidence_keeps_backward_compatible_csv_chunks(tmp_path: Path):
    csv_path = tmp_path / "retrieval_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query_id", "retrieved_chunks_json"])
        writer.writeheader()
        writer.writerow(
            {
                "query_id": "q1",
                "retrieved_chunks_json": json.dumps(
                    [{"url": "https://own.example", "brand": "Own", "text": "Old shape"}]
                ),
            }
        )

    evidence = load_retrieval_evidence(csv_path)

    assert evidence["q1"][0]["text"] == "Old shape"
