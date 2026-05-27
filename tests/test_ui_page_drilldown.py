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
    (report_dir / "url_top5_rankings.csv").write_text(
        "rank,url,domain,brand,title,source_type,top5_query_count,top5_hit_count,best_rank,avg_rank,models,personas,journey_stages,page_intent,signals\n"
        "1,https://horntech.com.au/pricing,horntech.com.au,HornTech,Pricing,competitor_site,7,9,1,1.4,model-a,founder,vendor_discovery,pricing,pricing\n",
        encoding="utf-8",
    )
    (report_dir / "domain_top5_rankings.csv").write_text(
        "rank,domain,brand,top5_query_count,top5_hit_count,best_rank,avg_rank,top_urls,models,personas,journey_stages,signals\n"
        "1,horntech.com.au,HornTech,7,9,1,1.4,https://horntech.com.au/pricing,model-a,founder,vendor_discovery,pricing\n",
        encoding="utf-8",
    )
    (report_dir / "persona_stage_losses.csv").write_text(
        "persona,journey_stage,query_count,target_top5_count,target_top5_share,not_ranked_count,leading_winner,winner_count,top_displacing_domain,top_displacing_url,top_displacing_url_count,primary_loss_reasons,recommended_action\n"
        "founder,vendor_discovery,10,2,20.0,8,HornTech,5,horntech.com.au,https://horntech.com.au/pricing,5,pricing,Add pricing proof\n",
        encoding="utf-8",
    )
    (report_dir / "page_intent_weakness.csv").write_text(
        "page_intent,page_count,weak_page_count,zero_top5_count,total_top5_queries,strongest_url,weakest_urls,recommended_focus\n"
        "pricing,2,1,1,0,,https://alphaxxxx.com/weak,Add pricing modules\n",
        encoding="utf-8",
    )
    (report_dir / "content_optimization_actions.csv").write_text(
        "priority,url,title,page_intent,target_persona,target_stage,problem,competitor_benchmark_url,competitor_benchmark_brand,content_gaps,internal_links_to_add,faq_questions,schema_recommendation,validation_metric\n"
        "P0,https://alphaxxxx.com/weak,Weak,pricing,founder,vendor_discovery,No Top5 retrieval,https://horntech.com.au/pricing,HornTech,pricing proof,Link from llms.txt,FAQ: cost?,FAQPage,Top5 >= 5\n",
        encoding="utf-8",
    )

    summary = summarize_report_page_drilldown(tmp_path, str(report_dir), target_brand="AlphaXXXX")

    assert summary["report_dir"] == str(report_dir)
    assert summary["top_pages"][0]["url"] == "https://alphaxxxx.com/service"
    assert summary["weak_pages"][0]["url"] == "https://alphaxxxx.com/weak"
    assert summary["url_rankings"][0]["domain"] == "horntech.com.au"
    assert summary["domain_rankings"][0]["domain"] == "horntech.com.au"
    assert summary["persona_stage_losses"][0]["target_top5_share"] == "20.0"
    assert summary["page_intent_groups"][0]["page_intent"] == "pricing"
    assert summary["content_actions"][0]["schema_recommendation"] == "FAQPage"


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
    assert summary["url_rankings"] == []
    assert summary["domain_rankings"] == []
    assert summary["persona_stage_losses"] == []
    assert summary["page_intent_groups"] == []
    assert summary["content_actions"] == []
