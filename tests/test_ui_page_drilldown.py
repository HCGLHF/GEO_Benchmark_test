import json
from pathlib import Path

from scripts.ui_app.page_drilldown_summary import summarize_report_page_drilldown


def test_summarize_report_page_drilldown_reads_existing_csvs(tmp_path: Path) -> None:
    report_dir = tmp_path / "runs" / "parallel" / "20260523_010000" / "merged"
    report_dir.mkdir(parents=True)
    (report_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
    (report_dir / "owned_top5_pages.csv").write_text(
        "url,title,top5_hit_count,top5_query_count,best_rank,model_count,persona_count,journey_stage_count,optimization_hint\n"
        "https://alphaxxxx.com/service,Service,2,2,2,2,1,1,Strong page\n",
        encoding="utf-8",
    )
    (report_dir / "owned_weak_pages.csv").write_text(
        "url,title,top5_hit_count,top5_query_count,best_rank,model_count,persona_count,journey_stage_count,optimization_hint\n"
        "https://alphaxxxx.com/weak,Weak,0,0,,0,0,0,No Top5 retrieval\n",
        encoding="utf-8",
    )

    summary = summarize_report_page_drilldown(tmp_path, str(report_dir), target_brand="AlphaXXXX")

    assert summary["report_dir"] == str(report_dir)
    assert summary["top_pages"][0]["url"] == "https://alphaxxxx.com/service"
    assert summary["weak_pages"][0]["url"] == "https://alphaxxxx.com/weak"


def test_summarize_report_page_drilldown_computes_for_legacy_report(tmp_path: Path) -> None:
    report_dir = tmp_path / "runs" / "parallel" / "20260523_010000" / "merged"
    report_dir.mkdir(parents=True)
    (report_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
    (report_dir / "retrieval_evidence_by_model.jsonl").write_text(
        json.dumps(
            {
                "query_id": "q001",
                "model": "openai/gpt-4.1-mini",
                "persona": "founder",
                "journey_stage": "vendor_discovery",
                "retrieved_chunks": [
                    {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/service", "title": "Service"}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "documents.jsonl").write_text(
        '{"url":"https://alphaxxxx.com/service","brand":"AlphaXXXX","title":"Service","content":"strong"}\n'
        '{"url":"https://alphaxxxx.com/weak","brand":"AlphaXXXX","title":"Weak","content":"thin"}\n',
        encoding="utf-8",
    )

    summary = summarize_report_page_drilldown(tmp_path, str(report_dir), target_brand="AlphaXXXX")

    assert summary["top_pages"][0]["url"] == "https://alphaxxxx.com/service"
    assert summary["weak_pages"][0]["url"] == "https://alphaxxxx.com/weak"
    assert summary["weak_pages"][0]["top5_query_count"] == 0
