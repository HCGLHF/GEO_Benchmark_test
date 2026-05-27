from __future__ import annotations

from pathlib import Path

from scripts.cloud.hydrate_artifacts import hydrate_artifacts, local_path_for_artifact


def artifact_row(artifact_type: str, object_key: str, bucket: str = "example-bucket") -> dict:
    return {
        "artifact_type": artifact_type,
        "industry_id": "geo-agency",
        "corpus_version": "2026-05-22-initial",
        "bucket": bucket,
        "object_key": object_key,
        "sha256": "0" * 64,
        "size_bytes": 12,
        "source_path": "ignored",
        "created_at": "2026-05-27T00:00:00Z",
    }


def test_local_path_for_artifact_restores_corpus_files(tmp_path: Path) -> None:
    root = tmp_path / "project"

    assert local_path_for_artifact(
        artifact_row(
            "url_inventory",
            "industries/geo-agency/raw/2026-05-22-initial/url_inventory.csv",
        ),
        root,
    ) == root / "data" / "raw" / "url_inventory.csv"
    assert local_path_for_artifact(
        artifact_row(
            "processed_documents",
            "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl",
        ),
        root,
    ) == root / "data" / "processed" / "documents.jsonl"


def test_local_path_for_artifact_restores_run_files(tmp_path: Path) -> None:
    root = tmp_path / "project"

    assert local_path_for_artifact(
        artifact_row(
            "competitive_gap_report",
            "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/reports/"
            "competitive_gap_report.md",
        ),
        root,
    ) == root / "runs" / "cloud_synced" / "quick" / "20260526_002837" / "merged" / "competitive_gap_report.md"
    assert local_path_for_artifact(
        artifact_row(
            "pipeline_state",
            "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/logs/pipeline_state.jsonl",
        ),
        root,
    ) == root / "runs" / "cloud_synced" / "quick" / "20260526_002837" / "pipeline_state.jsonl"


def test_local_path_for_artifact_restores_run_json_files(tmp_path: Path) -> None:
    root = tmp_path / "project"

    assert local_path_for_artifact(
        artifact_row(
            "report_deep_diagnostics",
            "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/json/"
            "report_deep_diagnostics.json",
        ),
        root,
    ) == root / "runs" / "cloud_synced" / "quick" / "20260526_002837" / "merged" / "report_deep_diagnostics.json"


def test_hydrate_artifacts_downloads_filtered_rows(tmp_path: Path) -> None:
    rows = [
        artifact_row("processed_documents", "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl"),
        artifact_row(
            "competitive_gap_report",
            "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/reports/"
            "competitive_gap_report.md",
        ),
        artifact_row(
            "competitive_gap_report",
            "industries/geo-agency/runs/2026-05-22-initial/test/20260523_031919/reports/"
            "competitive_gap_report.md",
        ),
    ]
    downloads: list[tuple[str, str, Path]] = []

    def fake_download(bucket: str, object_key: str, destination: Path) -> None:
        downloads.append((bucket, object_key, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(object_key, encoding="utf-8")

    result = hydrate_artifacts(
        artifact_rows=rows,
        project_root=tmp_path / "project",
        run_modes={"quick", "standard"},
        download_fn=fake_download,
    )

    assert result["status"] == "hydrated"
    assert result["summary"]["downloaded_count"] == 2
    assert len(downloads) == 2
    assert (tmp_path / "project" / "data" / "processed" / "documents.jsonl").exists()
    assert (
        tmp_path
        / "project"
        / "runs"
        / "cloud_synced"
        / "quick"
        / "20260526_002837"
        / "merged"
        / "competitive_gap_report.md"
    ).exists()


def test_hydrate_artifacts_skips_existing_files_by_default(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    existing_file = project_root / "data" / "processed" / "documents.jsonl"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text("local-newer-data", encoding="utf-8")
    rows = [
        artifact_row("processed_documents", "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl")
    ]
    downloads: list[Path] = []

    def fake_download(bucket: str, object_key: str, destination: Path) -> None:
        downloads.append(destination)
        destination.write_text("cloud-data", encoding="utf-8")

    result = hydrate_artifacts(
        artifact_rows=rows,
        project_root=project_root,
        run_modes={"quick", "standard"},
        download_fn=fake_download,
    )

    assert result["summary"]["downloaded_count"] == 0
    assert result["summary"]["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "exists"
    assert downloads == []
    assert existing_file.read_text(encoding="utf-8") == "local-newer-data"


def test_hydrate_artifacts_can_overwrite_existing_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    existing_file = project_root / "data" / "processed" / "documents.jsonl"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text("local-newer-data", encoding="utf-8")
    rows = [
        artifact_row("processed_documents", "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl")
    ]

    def fake_download(bucket: str, object_key: str, destination: Path) -> None:
        destination.write_text("cloud-data", encoding="utf-8")

    result = hydrate_artifacts(
        artifact_rows=rows,
        project_root=project_root,
        run_modes={"quick", "standard"},
        download_fn=fake_download,
        overwrite=True,
    )

    assert result["summary"]["downloaded_count"] == 1
    assert result["summary"]["skipped_count"] == 0
    assert existing_file.read_text(encoding="utf-8") == "cloud-data"
