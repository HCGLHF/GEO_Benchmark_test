from __future__ import annotations

import json
from pathlib import Path

import scripts.cloud.sync_run_artifacts as sync_module
from scripts.cloud.sync_run_artifacts import (
    build_run_artifact_plan,
    discover_run_reports,
    discover_run_roots,
    run_sync,
)


def write_report_run(
    run_root: Path,
    *,
    run_mode: str | None,
    query_rows: int,
    source_run_count: int,
    status: str = "completed",
    merged_name: str = "merged",
) -> Path:
    run_root.mkdir(parents=True)
    if run_mode is not None:
        (run_root / "run_manifest.json").write_text(
            json.dumps({"status": status, "metadata": {"run_mode": run_mode}}),
            encoding="utf-8",
        )
    merged = run_root / merged_name
    merged.mkdir()
    (merged / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
    (merged / "brand_performance_by_model.csv").write_text("brand,query_count\nAlphaXXXX,50\n", encoding="utf-8")
    (merged / "merge_manifest.json").write_text(
        json.dumps({"result": {"query_rows": query_rows, "source_run_count": source_run_count}}),
        encoding="utf-8",
    )
    return merged


def test_discover_run_roots_keeps_quick_and_standard(tmp_path: Path) -> None:
    quick = tmp_path / "runs" / "full_api_parallel_ui" / "20260526_002837"
    standard = tmp_path / "runs" / "full_api_parallel_ui" / "20260523_040450"
    test = tmp_path / "runs" / "full_api_parallel_ui" / "20260523_031919"
    failed = tmp_path / "runs" / "full_api_parallel_ui" / "20260523_060324"
    write_report_run(quick, run_mode="quick", query_rows=300, source_run_count=6)
    write_report_run(standard, run_mode="standard", query_rows=400, source_run_count=2)
    write_report_run(test, run_mode="test", query_rows=8, source_run_count=4)
    write_report_run(failed, run_mode="quick", query_rows=300, source_run_count=6, status="failed")

    roots = discover_run_roots([tmp_path / "runs" / "full_api_parallel_ui"], {"quick", "standard"})

    assert roots == [standard, quick]


def test_discover_run_reports_infers_legacy_quick_and_standard(tmp_path: Path) -> None:
    quick = tmp_path / "runs" / "full_api_parallel_alpha_refresh_quick_final" / "20260519_160422"
    standard = tmp_path / "runs" / "full_api_parallel" / "20260518_214558"
    test = tmp_path / "runs" / "full_api_parallel_ui" / "20260523_031919"
    quick_merged = write_report_run(quick, run_mode=None, query_rows=200, source_run_count=4)
    standard_merged = write_report_run(standard, run_mode=None, query_rows=600, source_run_count=3)
    write_report_run(test, run_mode=None, query_rows=8, source_run_count=4)

    reports = discover_run_reports(
        [
            tmp_path / "runs" / "full_api_parallel_alpha_refresh_quick_final",
            tmp_path / "runs" / "full_api_parallel",
            tmp_path / "runs" / "full_api_parallel_ui",
        ],
        {"quick", "standard"},
    )

    assert [(report.run_root, report.run_mode, report.merged_dir) for report in reports] == [
        (standard, "standard", standard_merged),
        (quick, "quick", quick_merged),
    ]


def test_build_run_artifact_plan_uses_stable_server_keys(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "full_api_parallel_ui" / "20260526_002837"
    merged = write_report_run(run_root, run_mode="quick", query_rows=250, source_run_count=5)
    (run_root / "pipeline_state.jsonl").write_text('{"stage":"report","status":"completed"}\n', encoding="utf-8")

    plan = build_run_artifact_plan(
        industry_id="geo-agency",
        corpus_version="2026-05-22-initial",
        run_root=run_root,
        run_mode="quick",
        merged_dir=merged,
    )

    keys = {item["artifact_type"]: item["object_key"] for item in plan["artifacts"]}
    assert keys["competitive_gap_report"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/reports/"
        "competitive_gap_report.md"
    )
    assert keys["brand_performance_by_model"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/tables/"
        "brand_performance_by_model.csv"
    )
    assert keys["merge_manifest"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/manifest/"
        "merge_manifest.json"
    )
    assert keys["pipeline_state"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/logs/"
        "pipeline_state.jsonl"
    )


def test_run_sync_execute_uses_injected_upload_and_register(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "runs" / "full_api_parallel_ui" / "20260526_002837"
    write_report_run(run_root, run_mode="quick", query_rows=250, source_run_count=5)
    uploads: list[str] = []
    registered: list[dict] = []
    monkeypatch.setattr(
        sync_module.CloudConfig,
        "from_env",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CloudConfig.from_env should not be used")),
    )

    def fake_upload(record: dict) -> dict:
        uploads.append(record["object_key"])
        return {**record, "bucket": "example-bucket"}

    def fake_register(records: list[dict]) -> None:
        registered.extend(records)

    result = run_sync(
        industry_id="geo-agency",
        corpus_version="2026-05-22-initial",
        run_roots=[tmp_path / "runs" / "full_api_parallel_ui"],
        run_modes={"quick"},
        execute=True,
        upload_fn=fake_upload,
        register_fn=fake_register,
    )

    assert result["status"] == "synced"
    assert result["summary"]["run_count"] == 1
    assert uploads
    assert registered
    assert all(record["bucket"] == "example-bucket" for record in registered)
