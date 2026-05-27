import csv
import json
from pathlib import Path

from scripts.compare_run_performance import build_brand_rows, write_outputs


def test_build_brand_rows_compares_target_against_retrieved_competitors(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "retrieval_evidence.jsonl").write_text(
        json.dumps(
            {
                "query_id": "q1",
                "retrieved_chunks": [
                    {"brand": "Competitor", "url": "https://competitor.example/a"},
                    {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/a"},
                    {"brand": "Competitor", "url": "https://competitor.example/b"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "model_responses.jsonl").write_text(
        json.dumps({"raw_answer": "Competitor is mentioned. AlphaXXXX is also mentioned.", "error": None})
        + "\n",
        encoding="utf-8",
    )

    rows = build_brand_rows(
        run_dir=run_dir,
        target_brand="AlphaXXXX",
        configured_brands=["Competitor"],
    )

    by_brand = {row["brand"]: row for row in rows}
    assert by_brand["AlphaXXXX"]["is_target"] == "True"
    assert by_brand["AlphaXXXX"]["top5_query_share"] == "100.0%"
    assert by_brand["AlphaXXXX"]["best_rank"] == 2
    assert by_brand["Competitor"]["top1_count"] == 1
    assert by_brand["Competitor"]["top10_slot_count"] == 2


def test_write_outputs_creates_csv_and_markdown(tmp_path: Path):
    rows = [
        {
            "brand": "AlphaXXXX",
            "is_target": "True",
            "query_count": 1,
            "top1_count": 0,
            "top5_count": 0,
            "top10_count": 0,
            "top10_slot_count": 0,
            "top5_query_share": "0.0%",
            "top10_query_share": "0.0%",
            "best_rank": "",
            "average_best_rank": "",
            "model_mention_count": 0,
            "model_mention_rate": "0.0%",
            "unique_url_count": 0,
            "top_urls_json": "[]",
        }
    ]

    csv_path = tmp_path / "brand_performance.csv"
    md_path = tmp_path / "brand_performance.md"
    write_outputs(rows, csv_path, md_path, "AlphaXXXX")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        persisted = list(csv.DictReader(handle))
    assert persisted[0]["brand"] == "AlphaXXXX"
    assert "AlphaXXXX" in md_path.read_text(encoding="utf-8")
