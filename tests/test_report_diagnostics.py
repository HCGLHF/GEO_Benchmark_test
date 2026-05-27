import csv
import json
from pathlib import Path

from scripts.report_diagnostics import (
    build_content_optimization_actions,
    build_competitor_displacements,
    build_domain_top5_rankings,
    build_page_optimization_plan,
    build_page_intent_weakness_groups,
    build_persona_stage_losses,
    build_query_loss_rows,
    build_url_top5_rankings,
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


def test_url_and_domain_top5_rankings_group_competitor_pages() -> None:
    evidence_rows = [
        {
            "query_id": "q1",
            "model": "model-a",
            "persona": "B2B SaaS founder",
            "journey_stage": "vendor_discovery",
            "retrieved_chunks": [
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/blog/ai-search-optimisation-sydney-2026-cost-guide",
                    "title": "AI Search Pricing Guide",
                    "source_type": "competitor_site",
                    "text_preview": "Sydney pricing free audit schema FAQ",
                },
                {
                    "brand": "AlphaXXXX",
                    "url": "https://alphaxxxx.com/llms.txt",
                    "title": "llms router",
                    "source_type": "owned_site",
                    "text_preview": "route to pricing and services",
                },
            ],
        },
        {
            "query_id": "q2",
            "model": "model-b",
            "persona": "B2B SaaS founder",
            "journey_stage": "solution_aware",
            "retrieved_chunks": [
                {
                    "brand": "Semrush AI Visibility Toolkit",
                    "url": "https://www.semrush.com/free-tools/ai-search-visibility-checker",
                    "title": "AI Search Visibility Checker",
                    "source_type": "industry_platform",
                    "text_preview": "tool pricing audit",
                },
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/blog/ai-search-optimisation-sydney-2026-cost-guide",
                    "title": "AI Search Pricing Guide",
                    "source_type": "competitor_site",
                    "text_preview": "Sydney pricing free audit schema FAQ",
                },
            ],
        },
    ]

    url_rows = build_url_top5_rankings("AlphaXXXX", evidence_rows, limit=5)
    domain_rows = build_domain_top5_rankings("AlphaXXXX", evidence_rows, limit=5)

    assert url_rows[0]["url"] == "https://horntech.com.au/blog/ai-search-optimisation-sydney-2026-cost-guide"
    assert url_rows[0]["domain"] == "horntech.com.au"
    assert url_rows[0]["top5_query_count"] == 2
    assert url_rows[0]["page_intent"] == "pricing"
    assert "pricing" in url_rows[0]["signals"]
    assert domain_rows[0]["domain"] == "horntech.com.au"
    assert domain_rows[0]["top_urls"].startswith("https://horntech.com.au/blog/")


def test_persona_stage_losses_identify_where_target_loses() -> None:
    retrieval_rows = [
        {
            "query_id": "q1",
            "query": "Need GEO pricing",
            "model": "model-a",
            "persona": "B2B SaaS founder",
            "journey_stage": "vendor_discovery",
            "own_brand_in_top_5": "False",
            "own_brand_rank": "",
            "winning_brand": "HornTech",
        },
        {
            "query_id": "q2",
            "query": "Need GEO audit",
            "model": "model-b",
            "persona": "B2B SaaS founder",
            "journey_stage": "vendor_discovery",
            "own_brand_in_top_5": "True",
            "own_brand_rank": "2",
            "winning_brand": "AlphaXXXX",
        },
    ]
    evidence_rows = [
        {
            "query_id": "q1",
            "model": "model-a",
            "persona": "B2B SaaS founder",
            "journey_stage": "vendor_discovery",
            "retrieved_chunks": [
                {
                    "brand": "HornTech",
                    "url": "https://horntech.com.au/pricing",
                    "title": "Pricing",
                    "text_preview": "pricing free audit",
                }
            ],
        }
    ]

    rows = build_persona_stage_losses("AlphaXXXX", retrieval_rows, evidence_rows)

    assert rows[0]["persona"] == "B2B SaaS founder"
    assert rows[0]["journey_stage"] == "vendor_discovery"
    assert rows[0]["query_count"] == 2
    assert rows[0]["target_top5_count"] == 1
    assert rows[0]["target_top5_share"] == 50.0
    assert rows[0]["leading_winner"] == "HornTech"
    assert rows[0]["top_displacing_domain"] == "horntech.com.au"
    assert "pricing" in rows[0]["primary_loss_reasons"]


def test_money_page_groups_and_actions_are_page_level() -> None:
    top_pages = [
        {
            "url": "https://alphaxxxx.com/llms.txt",
            "title": "llms router",
            "top5_query_count": 17,
            "top5_hit_count": 52,
            "model_count": 5,
        }
    ]
    weak_pages = [
        {
            "url": "https://alphaxxxx.com/geo-pricing",
            "title": "GEO Pricing",
            "top5_query_count": 0,
            "top5_hit_count": 0,
            "model_count": 0,
        },
        {
            "url": "https://alphaxxxx.com/blog/saas-founder-guide",
            "title": "SaaS Founder Guide",
            "top5_query_count": 1,
            "top5_hit_count": 2,
            "model_count": 1,
        },
    ]
    displacements = [
        {
            "winning_brand": "HornTech",
            "winning_url": "https://horntech.com.au/blog/ai-search-optimisation-sydney-2026-cost-guide",
            "winning_title": "Pricing guide",
            "top5_query_count": 7,
            "signals": "pricing, free audit, schema",
        }
    ]
    persona_stage_losses = [
        {
            "persona": "B2B SaaS founder",
            "journey_stage": "vendor_discovery",
            "primary_loss_reasons": "pricing, free audit",
        }
    ]

    groups = build_page_intent_weakness_groups(top_pages, weak_pages)
    actions = build_content_optimization_actions(
        target_brand="AlphaXXXX",
        weak_pages=weak_pages,
        displacements=displacements,
        persona_stage_losses=persona_stage_losses,
        limit=5,
    )

    assert groups[0]["page_intent"] == "pricing"
    assert groups[0]["weak_page_count"] == 1
    assert groups[0]["recommended_focus"]
    assert actions[0]["page_intent"] == "pricing"
    assert actions[0]["competitor_benchmark_url"] == displacements[0]["winning_url"]
    assert "FAQ" in actions[0]["faq_questions"]
    assert "FAQPage" in actions[0]["schema_recommendation"]
    assert "llms.txt" in actions[0]["internal_links_to_add"]
