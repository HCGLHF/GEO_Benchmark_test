from pathlib import Path

import pytest

from scripts.ui_app.report_history import list_report_history, read_report_download, read_report_preview


def _write_report(report_dir: Path, brand_rows: str, manifest: str = '{"result":{"query_rows":10,"answer_rows":8}}') -> None:
    report_dir.mkdir(parents=True)
    (report_dir / "competitive_gap_report.md").write_text("# Competitive Gap Report\n\nAlpha summary\n", encoding="utf-8")
    (report_dir / "merge_manifest.json").write_text(manifest, encoding="utf-8")
    (report_dir / "brand_performance_by_model.csv").write_text(
        "provider,model,brand,is_target,query_count,top5_count,top5_query_share,model_mention_rate,best_rank,average_best_rank\n"
        + brand_rows,
        encoding="utf-8",
    )


def test_list_report_history_returns_completed_reports_newest_first(tmp_path: Path) -> None:
    older = tmp_path / "runs" / "parallel" / "20260522_010000" / "merged"
    newer = tmp_path / "runs" / "parallel" / "20260523_010000" / "merged_3_models"
    _write_report(
        older,
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,10,1,10.0%,5.0%,2,2.0\n",
    )
    _write_report(
        newer,
        "openrouter,openai/gpt-4.1-mini,HornTech,False,10,6,60.0%,40.0%,1,1.2\n"
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,10,3,30.0%,10.0%,2,2.0\n",
        manifest='{"result":{"query_rows":10,"answer_rows":10}}',
    )
    older_report = older / "competitive_gap_report.md"
    newer_report = newer / "competitive_gap_report.md"
    older_time = 1_700_000_000
    newer_time = 1_700_000_100
    older_report.touch()
    newer_report.touch()
    import os

    os.utime(older_report, (older_time, older_time))
    os.utime(newer_report, (newer_time, newer_time))

    history = list_report_history(tmp_path, target_brand="AlphaXXXX", limit=10)

    assert [item.report_dir for item in history] == [newer, older]
    assert history[0].run_root == newer.parent
    assert history[0].answer_count == 10
    assert history[0].target_rank_by_top5 == 2
    assert history[0].target_top5_share == 30.0
    assert history[0].brands_above_target[0].brand == "HornTech"


def test_list_report_history_deduplicates_hydrated_reports_by_run_id(tmp_path: Path) -> None:
    local_newer = tmp_path / "runs" / "full_api_parallel_ui" / "20260526_002837" / "merged"
    cloud_duplicate = tmp_path / "runs" / "cloud_synced" / "quick" / "20260526_002837" / "merged"
    older_hydrated = tmp_path / "runs" / "cloud_synced" / "standard" / "20260523_040450" / "merged"
    for report_dir in [local_newer, cloud_duplicate, older_hydrated]:
        _write_report(
            report_dir,
            "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,10,3,30.0%,10.0%,2,2.0\n",
        )
    import os

    old_time = 1_700_000_000
    hydrated_download_time = 1_800_000_000
    os.utime(local_newer / "competitive_gap_report.md", (old_time, old_time))
    os.utime(cloud_duplicate / "competitive_gap_report.md", (hydrated_download_time, hydrated_download_time))
    os.utime(older_hydrated / "competitive_gap_report.md", (hydrated_download_time + 100, hydrated_download_time + 100))

    history = list_report_history(tmp_path, target_brand="AlphaXXXX", limit=10)

    assert [item.report_dir for item in history] == [local_newer, older_hydrated]
    assert history[0].updated_at.startswith("2026-05-26T00:28:37")


def test_read_report_preview_only_allows_known_report_dirs_under_runs(tmp_path: Path) -> None:
    report_dir = tmp_path / "runs" / "parallel" / "20260523_010000" / "merged"
    _write_report(
        report_dir,
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,10,3,30.0%,10.0%,2,2.0\n",
    )

    preview = read_report_preview(tmp_path, str(report_dir))

    assert preview["report_dir"] == str(report_dir)
    assert "Competitive Gap Report" in preview["content"]

    outside = tmp_path / "not-runs" / "merged"
    outside.mkdir(parents=True)
    (outside / "competitive_gap_report.md").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError):
        read_report_preview(tmp_path, str(outside))


def test_read_report_download_returns_known_markdown_report(tmp_path: Path) -> None:
    report_dir = tmp_path / "runs" / "parallel" / "20260523_010000" / "merged"
    _write_report(
        report_dir,
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,10,3,30.0%,10.0%,2,2.0\n",
    )

    download = read_report_download(tmp_path, str(report_dir))

    assert download["filename"] == "20260523_010000-competitive_gap_report.md"
    assert download["content_type"] == "text/markdown; charset=utf-8"
    assert "Competitive Gap Report" in download["content"]
