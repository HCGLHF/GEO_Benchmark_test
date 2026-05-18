import csv
import json
from pathlib import Path

from scripts.merge_full_api_runs import merge_full_api_runs


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def make_model_run(run_dir: Path, model: str, winning_brand: str) -> None:
    write_csv(
        run_dir / "api_queries.csv",
        [
            {
                "query_id": f"{model}-q1",
                "query": "Who can help with GEO?",
                "target_brand": "AlphaXXXX",
                "persona": "B2B SaaS founder",
                "journey_stage": "vendor_discovery",
                "scenario_provider": "openrouter",
                "scenario_model": model,
                "api_status": "success",
                "notes": "",
            }
        ],
        [
            "query_id",
            "query",
            "target_brand",
            "persona",
            "journey_stage",
            "scenario_provider",
            "scenario_model",
            "api_status",
            "notes",
        ],
    )
    write_csv(
        run_dir / "retrieval_by_model.csv",
        [
            {
                "run_id": f"run-{model}",
                "query_id": f"{model}-q1",
                "query": "Who can help with GEO?",
                "provider": "openrouter",
                "model": model,
                "persona": "B2B SaaS founder",
                "journey_stage": "vendor_discovery",
                "top_k": 10,
                "own_brand_rank": "",
                "own_brand_in_top_3": "False",
                "own_brand_in_top_5": "False",
                "own_brand_in_top_10": "False",
                "winning_brand": winning_brand,
                "winning_source_type": "competitor_site",
                "competitor_above_owned": "True",
                "matched_urls_json": "[]",
            }
        ],
        [
            "run_id",
            "query_id",
            "query",
            "provider",
            "model",
            "persona",
            "journey_stage",
            "top_k",
            "own_brand_rank",
            "own_brand_in_top_3",
            "own_brand_in_top_5",
            "own_brand_in_top_10",
            "winning_brand",
            "winning_source_type",
            "competitor_above_owned",
            "matched_urls_json",
        ],
    )
    write_jsonl(
        run_dir / "retrieval_evidence_by_model.jsonl",
        [
            {
                "query_id": f"{model}-q1",
                "query": "Who can help with GEO?",
                "provider": "openrouter",
                "model": model,
                "persona": "B2B SaaS founder",
                "journey_stage": "vendor_discovery",
                "retrieved_chunks": [
                    {
                        "brand": winning_brand,
                        "url": f"https://{winning_brand.lower()}.example",
                        "title": "GEO service",
                        "source_type": "competitor_site",
                        "text_preview": "GEO service Australia pricing ChatGPT",
                    }
                ],
            }
        ],
    )
    write_csv(
        run_dir / "model_answer_evaluations.csv",
        [
            {
                "query_id": f"{model}-q1",
                "query": "Who can help with GEO?",
                "provider": "openrouter",
                "model": model,
                "persona": "B2B SaaS founder",
                "journey_stage": "vendor_discovery",
                "raw_answer": f"{winning_brand} can help.",
                "brand_mentioned": "False",
                "recommended_own_brand": "False",
                "latency_ms": 10,
                "error": "",
            }
        ],
        [
            "query_id",
            "query",
            "provider",
            "model",
            "persona",
            "journey_stage",
            "raw_answer",
            "brand_mentioned",
            "recommended_own_brand",
            "latency_ms",
            "error",
        ],
    )


def test_merge_full_api_runs_rebuilds_outputs(tmp_path: Path):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    output = tmp_path / "merged"
    make_model_run(run_a, "model-a", "HornTech")
    make_model_run(run_b, "model-b", "OtterlyAI")

    result = merge_full_api_runs(
        run_dirs=[run_a, run_b],
        output_dir=output,
        target_brand="AlphaXXXX",
        configured_brands=["HornTech", "OtterlyAI"],
        corpus_stats={},
    )

    assert result["query_rows"] == 2
    assert result["retrieval_rows"] == 2
    assert (output / "competitive_gap_report.md").exists()
    with (output / "brand_performance_by_model.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["model"] for row in rows} == {"model-a", "model-b"}
    assert "HornTech" in (output / "competitive_gap_report.md").read_text(encoding="utf-8")
