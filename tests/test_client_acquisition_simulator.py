import json
from collections import Counter
from pathlib import Path

from scripts.client_acquisition_simulator import (
    build_answer_rows,
    build_brand_performance_by_model,
    build_competitive_gap_report,
    build_dimension_breakdown,
    build_rerank_prompt,
    default_scenario_matrix,
    generate_query_rows,
    parse_json_object,
    parse_rerank_response,
    rerank_candidates,
    sanitize_model_text,
    scenario_counts_for_model,
)


def sample_config(tmp_path: Path) -> dict:
    return {
        "campaign": {
            "target_brand": "AlphaXXXX",
            "target_domain": "alphaxxxx.com",
            "category": "Generative Engine Optimization services",
            "market": "Australia",
            "competitors": ["HornTech", "Semrush AI Visibility Toolkit"],
        },
        "run": {
            "output_dir": str(tmp_path / "run"),
            "top_k": 5,
            "candidate_pool_size": 3,
        },
        "client_acquisition": {
            "personas": ["SaaS founder"],
            "journey_stages": ["problem_aware"],
            "queries_per_stage": 1,
        },
        "models": [
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "api_key_env": "OPENROUTER_API_KEY",
            }
        ],
    }


def test_default_scenario_matrix_has_client_acquisition_stages():
    matrix = default_scenario_matrix({})

    assert "problem_aware" in matrix["journey_stages"]
    assert "vendor_discovery" in matrix["journey_stages"]
    assert "objection_handling" in matrix["journey_stages"]


def test_scenario_counts_for_model_distributes_exact_target():
    matrix = {
        "personas": ["p1", "p2", "p3"],
        "journey_stages": ["s1", "s2", "s3", "s4", "s5"],
        "queries_per_stage": 1,
        "queries_per_model": 200,
    }

    counts = scenario_counts_for_model(matrix)

    assert len(counts) == 15
    assert sum(count for _persona, _stage, count in counts) == 200
    assert Counter(count for _persona, _stage, count in counts) == Counter({13: 10, 14: 5})


def test_parse_json_object_extracts_json_from_model_text():
    parsed = parse_json_object('Here is JSON:\n{"queries": ["How do I get mentioned by ChatGPT?"]}')

    assert parsed["queries"] == ["How do I get mentioned by ChatGPT?"]


def test_sanitize_model_text_fixes_common_mojibake():
    assert sanitize_model_text("my company閳ユ獨 AI visibility") == "my company's AI visibility"
    assert sanitize_model_text("companyâ€™s visibility") == "company's visibility"


def test_generate_query_rows_uses_api_response_and_records_model(tmp_path):
    def fake_caller(model_config, prompt, temperature):
        return {
            "raw_answer": json.dumps({"queries": ["How can my SaaS get recommended by ChatGPT?"]}),
            "latency_ms": 12,
        }

    rows, attempts = generate_query_rows(sample_config(tmp_path), caller=fake_caller)

    assert rows[0]["query"] == "How can my SaaS get recommended by ChatGPT?"
    assert rows[0]["scenario_model"] == "openai/gpt-4.1-mini"
    assert rows[0]["persona"] == "SaaS founder"
    assert rows[0]["journey_stage"] == "problem_aware"
    assert attempts[0]["status"] == "success"
    assert attempts[0]["used_api"] is True


def test_generate_query_rows_falls_back_and_records_error(tmp_path):
    def failing_caller(model_config, prompt, temperature):
        raise RuntimeError("api unavailable")

    rows, attempts = generate_query_rows(sample_config(tmp_path), caller=failing_caller)

    assert rows[0]["query"]
    assert rows[0]["api_status"] == "fallback"
    assert attempts[0]["status"] == "error"


def test_generate_query_rows_creates_200_independent_queries_per_model(tmp_path):
    config = sample_config(tmp_path)
    config["client_acquisition"] = {
        "personas": ["p1", "p2", "p3"],
        "journey_stages": ["s1", "s2", "s3", "s4", "s5"],
        "queries_per_model": 200,
    }
    config["models"] = [
        {"provider": "openrouter", "model": "model-a"},
        {"provider": "openrouter", "model": "model-b"},
    ]

    def fake_caller(model_config, prompt, temperature):
        count = int(prompt.split("Number of queries: ")[1].split("\n")[0])
        return {"raw_answer": json.dumps({"queries": [f"{model_config['model']} query {index}" for index in range(count)]})}

    rows, attempts = generate_query_rows(config, caller=fake_caller)

    assert len(rows) == 400
    assert Counter(row["scenario_model"] for row in rows) == Counter({"model-a": 200, "model-b": 200})
    requested_by_model = Counter()
    for attempt in attempts:
        requested_by_model[attempt["model"]] += attempt["requested_query_count"]
    assert requested_by_model == Counter({"model-a": 200, "model-b": 200})


def test_build_rerank_prompt_contains_query_and_candidates():
    prompt = build_rerank_prompt(
        query="Who can help me get recommended by AI?",
        candidates=[
            {"candidate_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com", "title": "GEO"},
            {"candidate_id": "c2", "brand": "HornTech", "url": "https://horntech.com.au", "title": "GEO"},
        ],
        top_k=5,
    )

    assert "Who can help me get recommended by AI?" in prompt
    assert "c1" in prompt
    assert "ranked_candidate_ids" in prompt


def test_parse_rerank_response_orders_known_candidates_first():
    candidates = [
        {"candidate_id": "c1", "brand": "AlphaXXXX"},
        {"candidate_id": "c2", "brand": "HornTech"},
        {"candidate_id": "c3", "brand": "Semrush"},
    ]

    ranked = parse_rerank_response('{"ranked_candidate_ids": ["c2", "c1"]}', candidates)

    assert [item["candidate_id"] for item in ranked] == ["c2", "c1", "c3"]


def test_rerank_candidates_uses_api_order_and_calculates_metrics():
    def fake_caller(model_config, prompt, temperature):
        return {"raw_answer": '{"ranked_candidate_ids": ["c2", "c1"]}', "latency_ms": 7}

    rows, evidence, attempts = rerank_candidates(
        query_rows=[
            {
                "query_id": "q001",
                "query": "Who can help me get AI recommendations?",
                "target_brand": "AlphaXXXX",
                "scenario_model": "openai/gpt-4.1-mini",
                "scenario_provider": "openrouter",
                "persona": "SaaS founder",
                "journey_stage": "vendor_discovery",
            }
        ],
        candidates_by_query={
            "q001": [
                {"candidate_id": "c1", "chunk_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com", "source_type": "official_site"},
                {"candidate_id": "c2", "chunk_id": "c2", "brand": "HornTech", "url": "https://horntech.com.au", "source_type": "competitor_site"},
            ]
        },
        models=[{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
        top_k=5,
        caller=fake_caller,
    )

    assert rows[0]["model"] == "openai/gpt-4.1-mini"
    assert rows[0]["own_brand_rank"] == 2
    assert rows[0]["winning_brand"] == "HornTech"
    assert evidence[0]["retrieved_chunks"][0]["brand"] == "HornTech"
    assert attempts[0]["used_api"] is True


def test_rerank_candidates_keeps_each_model_on_its_own_queries():
    def fake_caller(model_config, prompt, temperature):
        return {"raw_answer": '{"ranked_candidate_ids": ["c1"]}', "latency_ms": 7}

    rows, evidence, attempts = rerank_candidates(
        query_rows=[
            {
                "query_id": "q001",
                "query": "Question from model A",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-a",
            },
            {
                "query_id": "q002",
                "query": "Question from model B",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-b",
            },
        ],
        candidates_by_query={
            "q001": [{"candidate_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com"}],
            "q002": [{"candidate_id": "c1", "brand": "HornTech", "url": "https://horntech.com.au"}],
        },
        models=[
            {"provider": "openrouter", "model": "model-a"},
            {"provider": "openrouter", "model": "model-b"},
        ],
        top_k=5,
        caller=fake_caller,
    )

    assert len(rows) == 2
    assert len(evidence) == 2
    assert len(attempts) == 2
    assert {(row["model"], row["query_id"]) for row in rows} == {("model-a", "q001"), ("model-b", "q002")}


def test_build_answer_rows_records_model_mentions():
    rows = build_answer_rows(
        query_rows=[{"query_id": "q001", "query": "Who can help?", "target_brand": "AlphaXXXX"}],
        models=[{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
        rerank_evidence=[
            {
                "query_id": "q001",
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "retrieved_chunks": [{"brand": "AlphaXXXX", "url": "https://alphaxxxx.com", "text_preview": "GEO agency"}],
            }
        ],
        caller=lambda model_config, prompt, temperature: {"raw_answer": "AlphaXXXX can help.", "latency_ms": 5},
    )

    assert rows[0]["brand_mentioned"] == "True"
    assert rows[0]["model"] == "openai/gpt-4.1-mini"


def test_build_brand_performance_by_model_groups_retrieval_and_answers():
    rows = build_brand_performance_by_model(
        target_brand="AlphaXXXX",
        configured_brands=["HornTech"],
        retrieval_evidence=[
            {
                "query_id": "q001",
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "retrieved_chunks": [
                    {"brand": "HornTech", "url": "https://horntech.com.au"},
                    {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com"},
                ],
            }
        ],
        answer_rows=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "brand_mentioned": "True",
                "raw_answer": "AlphaXXXX and HornTech are options.",
            }
        ],
    )

    target = next(row for row in rows if row["brand"] == "AlphaXXXX")
    horntech = next(row for row in rows if row["brand"] == "HornTech")
    assert target["top5_query_share"] == "100.0%"
    assert target["model_mention_rate"] == "100.0%"
    assert horntech["best_rank"] == 1


def test_build_dimension_breakdown_shows_weak_stage_and_winner():
    rows = build_dimension_breakdown(
        retrieval_rows=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "persona": "SaaS founder",
                "journey_stage": "vendor_discovery",
                "own_brand_in_top_5": "False",
                "winning_brand": "HornTech",
            }
        ],
        target_brand="AlphaXXXX",
    )

    assert rows[0]["dimension"] == "model"
    assert rows[0]["value"] == "openai/gpt-4.1-mini"
    assert rows[0]["target_top5_share"] == "0.0%"
    assert rows[0]["leading_winner"] == "HornTech"


def test_build_competitive_gap_report_lists_brands_above_target_and_gaps():
    report = build_competitive_gap_report(
        target_brand="AlphaXXXX",
        brand_rows=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "brand": "AlphaXXXX",
                "is_target": "True",
                "top5_query_share": "0.0%",
                "top10_query_share": "0.0%",
                "model_mention_rate": "0.0%",
                "top10_slot_count": 0,
                "best_rank": "",
                "top_urls_json": "[]",
            },
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "brand": "HornTech",
                "is_target": "False",
                "top5_query_share": "100.0%",
                "top10_query_share": "100.0%",
                "model_mention_rate": "100.0%",
                "top10_slot_count": 2,
                "best_rank": 1,
                "top_urls_json": json.dumps(["https://horntech.com.au/ai-development-services"]),
            },
        ],
        retrieval_rows=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "persona": "SaaS founder",
                "journey_stage": "vendor_discovery",
                "own_brand_in_top_5": "False",
                "winning_brand": "HornTech",
            }
        ],
        retrieval_evidence=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "query": "How do I get AI recommendations?",
                "retrieved_chunks": [
                    {
                        "brand": "HornTech",
                        "url": "https://horntech.com.au/ai-development-services",
                        "title": "AI Development Services",
                        "text_preview": "custom AI development services, workflow automation, GEO optimization, pricing",
                    }
                ],
            }
        ],
        answer_rows=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-4.1-mini",
                "raw_answer": "HornTech can help.",
                "brand_mentioned": "False",
            }
        ],
        corpus_stats={
            "AlphaXXXX": {"document_count": 1, "chunk_count": 2, "url_count": 1},
            "HornTech": {"document_count": 20, "chunk_count": 50, "url_count": 20},
        },
    )

    assert "Brands Above AlphaXXXX" in report
    assert "Likely Gaps vs Winners" in report
    assert "HornTech" in report
    assert "custom AI development services" in report
    assert "Content Gap Signals" in report
