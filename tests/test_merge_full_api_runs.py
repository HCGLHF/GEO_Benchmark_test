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


def make_model_run(run_dir: Path, model: str, winning_brand: str, include_owned: bool = False) -> None:
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
                ]
                + (
                    [
                        {
                            "brand": "AlphaXXXX",
                            "url": "https://alphaxxxx.com/service",
                            "title": "Alpha Service",
                            "source_type": "owned_site",
                            "text_preview": "Alpha GEO service",
                        }
                    ]
                    if include_owned
                    else []
                ),
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


def test_merge_full_api_runs_writes_owned_page_drilldown(tmp_path: Path):
    run_a = tmp_path / "run_a"
    output = tmp_path / "merged"
    make_model_run(run_a, "model-a", "HornTech", include_owned=True)

    merge_full_api_runs(
        run_dirs=[run_a],
        output_dir=output,
        target_brand="AlphaXXXX",
        configured_brands=["HornTech"],
        corpus_stats={},
        owned_pages=[
            {"url": "https://alphaxxxx.com/service", "title": "Alpha Service", "content_length": 500},
            {"url": "https://alphaxxxx.com/weak", "title": "Weak Page", "content_length": 100},
        ],
    )

    assert (output / "owned_top5_pages.csv").exists()
    assert (output / "owned_weak_pages.csv").exists()
    report = (output / "competitive_gap_report.md").read_text(encoding="utf-8")
    assert "AlphaXXXX Top5 Retrieved Pages" in report
    assert "https://alphaxxxx.com/service" in report
    assert "AlphaXXXX Weak Pages To Optimize" in report
    assert "https://alphaxxxx.com/weak" in report


def test_merge_full_api_runs_writes_diagnostic_report_sections(tmp_path: Path):
    run_a = tmp_path / "run_a"
    output = tmp_path / "merged"
    make_model_run(run_a, "model-a", "HornTech", include_owned=True)

    merge_full_api_runs(
        run_dirs=[run_a],
        output_dir=output,
        target_brand="AlphaXXXX",
        configured_brands=["HornTech"],
        corpus_stats={},
        owned_pages=[
            {"url": "https://alphaxxxx.com/service", "title": "Alpha Service", "content_length": 500},
            {"url": "https://alphaxxxx.com/weak", "title": "Weak Page", "content_length": 100},
        ],
    )

    assert (output / "query_loss_analysis.csv").exists()
    assert (output / "competitor_displacements.csv").exists()
    assert (output / "page_optimization_plan.csv").exists()
    assert (output / "url_top5_rankings.csv").exists()
    assert (output / "domain_top5_rankings.csv").exists()
    assert (output / "persona_stage_losses.csv").exists()
    assert (output / "page_intent_weakness.csv").exists()
    assert (output / "content_optimization_actions.csv").exists()
    assert (output / "report_deep_diagnostics.json").exists()
    with (output / "report_deep_diagnostics.json").open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["url_top5_rankings"]
    assert payload["domain_top5_rankings"]
    assert payload["persona_stage_losses"]
    assert payload["content_optimization_actions"]
    report = (output / "competitive_gap_report.md").read_text(encoding="utf-8")
    assert "Executive Diagnosis" in report
    assert "URL-Level Top5 Winners" in report
    assert "Domain-Level Top5 Winners" in report
    assert "Persona/Stage Loss Matrix" in report
    assert "Money Page Weakness Groups" in report
    assert "Page-Level Action Plan" in report
    assert "Query-Level Loss Analysis" in report
    assert "Competitor Pages Displacing AlphaXXXX" in report
    assert "Priority Optimization Plan" in report
    assert "AlphaXXXX Weakness Diagnosis" in report
    assert "Competitor pages are repeatedly displacing AlphaXXXX" in report


def test_merge_full_api_runs_appends_model_warning_section(tmp_path: Path):
    run_a = tmp_path / "qwen_qwen3.7-max"
    output = tmp_path / "merged"
    make_model_run(run_a, "qwen/qwen3.7-max", "HornTech", include_owned=True)
    write_jsonl(
        run_a / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "answer",
                "model": "qwen/qwen3.7-max",
                "status": "error",
                "query_id": "qwen/qwen3.7-max-q1",
                "error": "OpenRouter 429 Too Many Requests",
            }
        ],
    )

    merge_full_api_runs(
        run_dirs=[run_a],
        output_dir=output,
        target_brand="AlphaXXXX",
        configured_brands=["HornTech"],
        corpus_stats={},
        owned_pages=[],
    )

    report = (output / "competitive_gap_report.md").read_text(encoding="utf-8")
    assert "Model Warnings" in report
    assert "Qwen had 1 rate-limit failure; interpret with caution." in report
