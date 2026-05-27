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
    assert summary.model_breakdowns[0].leading_winner == "HornTech"


def test_summarize_latest_report_handles_missing_report(tmp_path: Path) -> None:
    summary = summarize_latest_report(tmp_path, target_brand="AlphaXXXX")

    assert summary.report_dir is None
    assert summary.target_rank_by_top5 is None
    assert summary.brands_above_target == []
