from pathlib import Path

from scripts.ui_app.report_summary import summarize_latest_report


def test_summarize_latest_report_finds_target_rank_and_competitors(tmp_path: Path) -> None:
    merged = tmp_path / "runs" / "sample" / "merged"
    merged.mkdir(parents=True)
    (merged / "merge_manifest.json").write_text('{"result":{"query_rows":100,"answer_rows":100}}', encoding="utf-8")
    (merged / "brand_performance_by_model.csv").write_text(
        "provider,model,brand,is_target,query_count,top5_count,top5_query_share,model_mention_rate,best_rank,average_best_rank\n"
        "openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,50,10,20.0%,12.0%,1,3.0\n"
        "openrouter,openai/gpt-4.1-mini,HornTech,False,50,40,80.0%,60.0%,1,2.0\n"
        "openrouter,openai/gpt-4.1-mini,OtterlyAI,False,50,30,60.0%,50.0%,1,2.5\n",
        encoding="utf-8",
    )
    (merged / "dimension_breakdown.csv").write_text(
        "dimension,value,query_count,target_top5_count,target_top5_share,leading_winner,winner_count\n"
        "model,openai/gpt-4.1-mini,50,10,20.0%,HornTech,20\n",
        encoding="utf-8",
    )

    summary = summarize_latest_report(tmp_path, target_brand="AlphaXXXX")

    assert summary.report_dir == merged
    assert summary.query_count == 100
    assert summary.answer_count == 100
    assert summary.target_top5_share == 20.0
    assert summary.target_rank_by_top5 == 3
    assert [brand.brand for brand in summary.brands_above_target] == ["HornTech", "OtterlyAI"]
    assert [brand.brand for brand in summary.top_brands] == ["HornTech", "OtterlyAI", "AlphaXXXX"]
    assert summary.model_breakdowns[0].leading_winner == "HornTech"


def test_summarize_latest_report_handles_missing_report(tmp_path: Path) -> None:
    summary = summarize_latest_report(tmp_path, target_brand="AlphaXXXX")

    assert summary.report_dir is None
    assert summary.target_rank_by_top5 is None
    assert summary.brands_above_target == []
    assert summary.top_brands == []


def test_summarize_latest_report_returns_top_five_brands(tmp_path: Path) -> None:
    merged = tmp_path / "runs" / "sample" / "merged"
    merged.mkdir(parents=True)
    (merged / "merge_manifest.json").write_text('{"result":{"query_rows":60,"answer_rows":60}}', encoding="utf-8")
    rows = [
        ("HornTech", 50, 45, "90.0%", "70.0%"),
        ("Semrush", 50, 35, "70.0%", "40.0%"),
        ("OtterlyAI", 50, 30, "60.0%", "50.0%"),
        ("AlphaXXXX", 50, 25, "50.0%", "30.0%"),
        ("PeecAI", 50, 20, "40.0%", "20.0%"),
        ("Profound", 50, 10, "20.0%", "10.0%"),
    ]
    body = "".join(
        f"openrouter,openai/gpt-4.1-mini,{brand},False,{queries},{top5},{share},{mention},1,2.0\n"
        for brand, queries, top5, share, mention in rows
    )
    (merged / "brand_performance_by_model.csv").write_text(
        "provider,model,brand,is_target,query_count,top5_count,top5_query_share,model_mention_rate,best_rank,average_best_rank\n"
        + body,
        encoding="utf-8",
    )

    summary = summarize_latest_report(tmp_path, target_brand="AlphaXXXX")

    assert [brand.brand for brand in summary.top_brands] == ["HornTech", "Semrush", "OtterlyAI", "AlphaXXXX", "PeecAI"]
    assert summary.top_brands[0].top5_share == 90.0
    assert summary.top_brands[0].model_mention_rate == 70.0


def test_summarize_latest_report_uses_run_id_over_hydrate_mtime(tmp_path: Path) -> None:
    newer = tmp_path / "runs" / "full_api_parallel_ui" / "20260526_002837" / "merged"
    older_hydrated = tmp_path / "runs" / "cloud_synced" / "standard" / "20260523_040450" / "merged"
    for report_dir, query_count in [(newer, 250), (older_hydrated, 400)]:
        report_dir.mkdir(parents=True)
        (report_dir / "merge_manifest.json").write_text(
            f'{{"result":{{"query_rows":{query_count},"answer_rows":{query_count}}}}}',
            encoding="utf-8",
        )
        (report_dir / "brand_performance_by_model.csv").write_text(
            "provider,model,brand,is_target,query_count,top5_count,top5_query_share,model_mention_rate,best_rank,average_best_rank\n"
            f"openrouter,openai/gpt-4.1-mini,AlphaXXXX,True,{query_count},10,4.0%,2.0%,1,3.0\n",
            encoding="utf-8",
        )
    import os

    old_time = 1_700_000_000
    hydrated_download_time = 1_800_000_000
    os.utime(newer / "brand_performance_by_model.csv", (old_time, old_time))
    os.utime(older_hydrated / "brand_performance_by_model.csv", (hydrated_download_time, hydrated_download_time))

    summary = summarize_latest_report(tmp_path, target_brand="AlphaXXXX")

    assert summary.report_dir == newer
    assert summary.query_count == 250
