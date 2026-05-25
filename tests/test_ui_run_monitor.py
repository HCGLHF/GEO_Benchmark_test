import json
from pathlib import Path

from scripts.ui_app.run_monitor import parse_pipeline_progress, summarize_parallel_run


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_summarize_parallel_run_reads_model_progress_logs_and_report(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260522_120000"
    model_dir = run_root / "openai_gpt-4.1-mini"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
                "client_acquisition": {"queries_per_model": 2},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text(
        "query_id,scenario_model,query\nq0001,openai/gpt-4.1-mini,Need GEO\n",
        encoding="utf-8",
    )
    (model_dir / "retrieval_by_model.csv").write_text(
        "query_id,model,own_brand_rank\nq0001,openai/gpt-4.1-mini,3\n",
        encoding="utf-8",
    )
    (model_dir / "worker.log").write_text("line 1\nline 2\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "rerank",
                "model": "openai/gpt-4.1-mini",
                "status": "api_call",
                "created_at": "2026-05-22T04:00:00Z",
            }
        ],
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_type": "full_api_parallel",
                "stages": ["crawl", "clean", "chunk", "index", "AWS sync", "rerank", "answer", "merge", "report"],
                "models": ["openai/gpt-4.1-mini"],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        run_root / "pipeline_state.jsonl",
        [
            {"stage": "crawl", "status": "completed", "message": "Crawl done", "details": {"urls": 37}},
            {"stage": "rerank", "status": "running", "message": "Reranking"},
        ],
    )
    merged = run_root / "merged"
    merged.mkdir()
    (merged / "merge_manifest.json").write_text('{"result":{"query_rows":1,"answer_rows":0}}', encoding="utf-8")
    (merged / "brand_performance_by_model.csv").write_text(
        "provider,model,brand,is_target,query_count,top5_count,top5_query_share,model_mention_rate,best_rank,average_best_rank\n"
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,1,1,100.0%,0.0%,3,3.0\n",
        encoding="utf-8",
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["run_root"] == str(run_root)
    assert summary["current_stage"] == "rerank"
    assert summary["pipeline"]["current_stage"] == "rerank"
    assert summary["pipeline"]["stages"]["crawl"]["details"]["urls"] == 37
    assert summary["totals"]["api_calls"] == 1
    assert summary["health"]["status"] == "warning"
    assert any("missing answer rows" in issue.lower() for issue in summary["health"]["issues"])
    assert summary["models"][0]["model_dir"] == str(model_dir)
    assert summary["models"][0]["log_tail"] == ["line 1", "line 2"]
    assert summary["report"]["target_rank_by_top5"] == 1


def test_summarize_parallel_run_includes_pipeline_log_tails(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "ui_pipeline" / "20260522_120000"
    log_path = run_root / "logs" / "owned_site_crawl.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("discovering\nProgress: 10/37 crawled\nCrawled 37 successful pages from 37 URLs\n", encoding="utf-8")
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_type": "ui_pipeline",
                "stages": ["owned_site_crawl", "clean"],
                "models": [],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        run_root / "pipeline_state.jsonl",
        [
            {
                "stage": "owned_site_crawl",
                "status": "running",
                "message": "Started",
                "details": {"log_path": str(log_path)},
            }
        ],
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["current_stage"] == "owned_site_crawl"
    assert summary["pipeline_log_tails"][0]["stage"] == "owned_site_crawl"
    assert summary["pipeline_log_tails"][0]["lines"][-1] == "Crawled 37 successful pages from 37 URLs"
    assert summary["pipeline_progress"]["owned_site_crawl"] == {
        "completed": 37,
        "total": 37,
        "percent": 100.0,
        "label": "37/37 pages",
    }


def test_parse_pipeline_progress_reads_active_recrawl_log() -> None:
    progress = parse_pipeline_progress(
        [
            "Discovering AlphaXXXX URLs from 1 seed URL(s)...",
            "Discovered 41 URLs -> data/raw/alpha_update_discovered_urls.csv",
            "Fetching discovered pages with local crawler...",
            "Progress: 10/41 crawled, 9 successful",
            "Progress: 20/41 crawled, 18 successful",
        ]
    )

    assert progress == {
        "completed": 20,
        "total": 41,
        "percent": 48.8,
        "label": "20/41 pages",
    }


def test_summarize_parallel_run_decodes_utf16_worker_logs(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260522_120000"
    model_dir = run_root / "deepseek_deepseek-chat"
    model_dir.mkdir(parents=True)
    (model_dir / "worker.log").write_text('{"queries": 50}\nReport: ok\n', encoding="utf-16")

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["models"][0]["log_tail"] == ['{"queries": 50}', "Report: ok"]


def test_summarize_parallel_run_reports_failed_worker_health(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260522_120000"
    model_dir = run_root / "openai_gpt-4.1-mini"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "worker_exit_code.txt").write_text("1", encoding="utf-8")
    (model_dir / "worker.log").write_text("Provider returned 429\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "answer",
                "model": "openai/gpt-4.1-mini",
                "status": "error",
                "query_id": "q001",
                "error": "Provider returned 429",
                "created_at": "2026-05-22T04:00:00Z",
            }
        ],
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["health"]["status"] == "error"
    assert any("openai_gpt-4.1-mini exited with code 1" in issue for issue in summary["health"]["issues"])
    assert any("api failures" in issue.lower() for issue in summary["health"]["issues"])


def test_summarize_parallel_run_downgrades_stale_parent_failure_when_workers_completed(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260522_120000"
    for safe_name in ["openai_gpt-4.1-mini", "deepseek_deepseek-chat"]:
        model_dir = run_root / safe_name
        model_dir.mkdir(parents=True)
        (model_dir / "run_config.resolved.json").write_text(
            json.dumps(
                {
                    "models": [{"provider": "openrouter", "model": safe_name.replace("_", "/")}],
                    "client_acquisition": {"queries_per_model": 1},
                }
            ),
            encoding="utf-8",
        )
        (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
        (model_dir / "retrieval_by_model.csv").write_text("query_id,model\nq001,model\n", encoding="utf-8")
        (model_dir / "model_answer_evaluations.csv").write_text("query_id,model,error\nq001,model,\n", encoding="utf-8")
        (model_dir / "worker_exit_code.txt").write_text("0", encoding="utf-8")
        write_jsonl(
            model_dir / "api_orchestrator_attempts.jsonl",
            [
                {"task_type": "rerank", "model": safe_name, "status": "api_call"},
                {"task_type": "answer", "model": safe_name, "status": "api_call"},
            ],
        )
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_type": "full_api_parallel", "stages": ["answer"], "models": []}),
        encoding="utf-8",
    )
    write_jsonl(
        run_root / "pipeline_state.jsonl",
        [{"stage": "answer", "status": "failed", "message": "One or more model workers failed."}],
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["health"]["status"] == "warning"
    assert any("parent pipeline marked answer failed" in issue.lower() for issue in summary["health"]["issues"])


def test_summarize_parallel_run_caps_total_progress_at_one(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260522_120000"
    model_dir = run_root / "openai_gpt-4.1-mini"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {"task_type": "rerank", "model": "openai/gpt-4.1-mini", "status": "api_call"},
            {"task_type": "answer", "model": "openai/gpt-4.1-mini", "status": "api_call"},
            {"task_type": "answer", "model": "openai/gpt-4.1-mini", "status": "cache_hit"},
        ],
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["totals"]["terminal_calls"] == 3
    assert summary["totals"]["expected_api_calls"] == 2
    assert summary["totals"]["progress"] == 1.0
