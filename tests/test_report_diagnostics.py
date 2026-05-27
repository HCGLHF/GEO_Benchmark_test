import csv
import json
from pathlib import Path

from scripts.report_diagnostics import (
    build_competitor_displacements,
    build_page_optimization_plan,
    build_query_loss_rows,
    render_diagnostic_sections,
)


def test_query_loss_rows_explain_winning_competitor_page() -> None:
    retrieval_rows = [
        {
            "query_id": "q1",
            "query": "Who can help a Sydney business get AI recommendations?",
            "model": "google/gemini-2.5-flash",
            "persona": "local service business owner",
            "journey_stage": "vendor_discovery",
            "own_brand_rank": "",
            "own_brand_in_top_5": "False",
            "winning_brand": "HornTech",
        }
    ]
    evidence_rows = [
        {
            "query_id": "q1",
            "query": "Who can help a Sydney business get AI recommendations?",
            "model": "google/gemini-2.5-flash",
            "persona": "local service business owner",
            "journey_stage": "vendor_discovery",
            "retrieved_chunks": [
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/sydney-ai-search",
                    "title": "Sydney AI search pricing guide",
                    "text_preview": "Sydney businesses can get found in AI search engines with pricing and a free audit.",
                },
                {
                    "brand": "AlphaXXXX",
                    "url": "https://alphaxxxx.com/ai-search-optimization-sydney",
                    "title": "AI Search Optimization Sydney",
                    "text_preview": "AI search visibility services.",
                },
            ],
        }
    ]

    rows = build_query_loss_rows("AlphaXXXX", retrieval_rows, evidence_rows, limit=5)

    assert rows == [
        {
            "query_id": "q1",
            "query": "Who can help a Sydney business get AI recommendations?",
            "model": "google/gemini-2.5-flash",
            "persona": "local service business owner",
            "journey_stage": "vendor_discovery",
            "target_rank": "2",
            "winning_brand": "HornTech",
            "winning_url": "https://horntech.com.au/sydney-ai-search",
            "winning_title": "Sydney AI search pricing guide",
            "loss_reason": "Sydney, pricing, free audit, get found in AI search engines",
        }
    ]


def test_competitor_displacements_group_repeated_winning_urls() -> None:
    evidence_rows = [
        {
            "query_id": "q1",
            "model": "model-a",
            "persona": "SEO agency owner",
            "journey_stage": "problem_aware",
            "retrieved_chunks": [
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/questions",
                    "title": "14 questions before spending",
                    "text_preview": "pricing free audit Sydney questions before spending",
                }
            ],
        },
        {
            "query_id": "q2",
            "model": "model-b",
            "persona": "local service business owner",
            "journey_stage": "vendor_discovery",
            "retrieved_chunks": [
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/questions",
                    "title": "14 questions before spending",
                    "text_preview": "pricing free audit Sydney questions before spending",
                }
            ],
        },
    ]

    rows = build_competitor_displacements("AlphaXXXX", evidence_rows, limit=3)

    assert rows[0]["winning_brand"] == "HornTech"
    assert rows[0]["winning_url"] == "https://horntech.com.au/questions"
    assert rows[0]["top5_query_count"] == 2
    assert rows[0]["models"] == "model-a, model-b"
    assert rows[0]["signals"] == "Sydney, pricing, free audit"


def test_page_optimization_plan_prioritizes_unretrieved_owned_pages() -> None:
    weak_pages = [
        {
            "url": "https://alphaxxxx.com/ai-search-optimization-sydney",
            "title": "AI Search Optimization Sydney",
            "top5_query_count": 0,
            "model_count": 0,
        },
        {
            "url": "https://alphaxxxx.com/blog",
            "title": "blog",
            "top5_query_count": 3,
            "model_count": 1,
        },
    ]

    plan = build_page_optimization_plan(weak_pages, limit=2)

    assert plan[0]["priority"] == "P0"
    assert plan[0]["url"] == "https://alphaxxxx.com/ai-search-optimization-sydney"
    assert "Sydney/local AI recommendation intent" in plan[0]["recommended_modules"]
    assert plan[1]["priority"] == "P2"


def test_render_diagnostic_sections_includes_actionable_tables(tmp_path: Path) -> None:
    query_losses = [
        {
            "query_id": "q1",
            "query": "Who can help with GEO?",
            "model": "model-a",
            "persona": "SEO agency owner",
            "journey_stage": "vendor_discovery",
            "target_rank": "not ranked",
            "winning_brand": "HornTech",
            "winning_url": "https://horntech.com.au/questions",
            "winning_title": "Questions",
            "loss_reason": "pricing",
        }
    ]
    displacements = [
        {
            "winning_brand": "HornTech",
            "winning_url": "https://horntech.com.au/questions",
            "winning_title": "Questions",
            "top5_query_count": 2,
            "models": "model-a",
            "personas": "SEO agency owner",
            "journey_stages": "vendor_discovery",
            "signals": "pricing",
        }
    ]
    page_plan = [
        {
            "priority": "P0",
            "url": "https://alphaxxxx.com/geo-pricing",
            "title": "Pricing",
            "problem": "No Top5 retrieval",
            "recommended_modules": "Pricing proof",
            "validation_metric": "Top5 query count >= 5",
        }
    ]

    markdown = render_diagnostic_sections(
        target_brand="AlphaXXXX",
        query_losses=query_losses,
        displacements=displacements,
        page_plan=page_plan,
        source_run_count=2,
        answer_count=400,
    )

    assert "## Executive Diagnosis" in markdown
    assert "## Query-Level Loss Analysis" in markdown
    assert "HornTech" in markdown
    assert "## Priority Optimization Plan" in markdown
    assert "This report uses 2 completed model run(s)" in markdown
