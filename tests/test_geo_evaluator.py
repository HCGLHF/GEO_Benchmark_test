import csv
import json

from scripts.geo_evaluator import (
    build_summary,
    build_chat_payload,
    compact_retrieval_row,
    evaluate_answer_rows,
    generate_query_plans,
    generate_scenarios,
    model_summary_rows,
    model_response_key,
    provider_endpoint,
    retrieval_summary,
    should_run_direct,
    write_queries_csv,
)
from scripts._common import RetrievalResultRecord


def sample_config(tmp_path):
    return {
        "campaign": {
            "name": "alpha_geo_audit",
            "market": "US",
            "language": "en",
            "category": "Generative Engine Optimization software and services",
            "target_brand": "AlphaXXXX",
            "target_domain": "alphaxxxx.com",
            "competitors": ["Profound", "OtterlyAI"],
            "buyer_profiles": ["B2B SaaS founder", "Marketing director"],
        },
        "run": {
            "scenarios_per_profile": 2,
            "output_dir": str(tmp_path / "run"),
            "top_k": 5,
        },
        "retrieval": {
            "keyword_index": "data/processed/bm25_index.pkl",
            "sqlite": str(tmp_path / "geo.sqlite"),
        },
    }


def test_generate_scenarios_is_deterministic_and_uses_campaign_context(tmp_path):
    scenarios = generate_scenarios(sample_config(tmp_path))

    assert len(scenarios) == 4
    assert scenarios[0]["id"] == "sc001"
    assert scenarios[0]["buyer_profile"] == "B2B SaaS founder"
    assert "AlphaXXXX" not in scenarios[0]["raw_question"]
    assert "Generative Engine Optimization" in scenarios[0]["rewritten_task"]


def test_generate_query_plans_creates_eval_queries_csv_shape(tmp_path):
    config = sample_config(tmp_path)
    scenarios = generate_scenarios(config)
    plans = generate_query_plans(config, scenarios)
    output = tmp_path / "queries.csv"

    rows = write_queries_csv(output, config, plans)

    assert rows[0]["query_id"] == "q001"
    assert rows[0]["target_brand"] == "AlphaXXXX"
    assert rows[0]["intent"]
    with output.open("r", encoding="utf-8", newline="") as handle:
        persisted = list(csv.DictReader(handle))
    assert persisted == rows


def test_retrieval_summary_calculates_recall_and_competitor_win_rate():
    rows = [
        {"own_brand_in_top_5": "True", "competitor_above_owned": "False"},
        {"own_brand_in_top_5": "False", "competitor_above_owned": "True"},
    ]

    summary = retrieval_summary(rows)

    assert summary["query_count"] == 2
    assert summary["recall_at_5"] == 0.5
    assert summary["competitor_win_rate"] == 0.5


def test_build_summary_includes_recall_and_weak_query_urls():
    rows = [
        {
            "query_id": "q001",
            "query": "best geo platform",
            "own_brand_rank": "",
            "own_brand_in_top_5": "False",
            "competitor_above_owned": "True",
            "matched_urls_json": json.dumps(["https://competitor.example"]),
        }
    ]

    report = build_summary({"campaign": {"target_brand": "AlphaXXXX"}}, rows)

    assert "Recall@5: 0.0%" in report
    assert "Competitor Win Rate: 100.0%" in report
    assert "https://competitor.example" in report


def test_compact_retrieval_row_keeps_metrics_without_chunk_payload():
    record = RetrievalResultRecord(
        run_id="run_1",
        query_id="q001",
        query="best geo platform",
        top_k=5,
        own_brand_rank=None,
        own_brand_in_top_3=False,
        own_brand_in_top_5=False,
        own_brand_in_top_10=False,
        winning_brand="Competitor",
        winning_source_type="industry_platform",
        competitor_above_owned=True,
        matched_urls_json=json.dumps(["https://competitor.example"]),
        retrieved_chunks_json=json.dumps([{"text": "x" * 1000}]),
    )

    row = compact_retrieval_row(record)

    assert row["matched_urls_json"] == json.dumps(["https://competitor.example"])
    assert "retrieved_chunks_json" not in row


def test_should_run_direct_blocks_below_recall_threshold():
    config = {"model_run": {"direct": {"enabled": True, "recall_gate": "block", "min_recall_at_5": 0.5}}}

    allowed, reason = should_run_direct(config, {"recall_at_5": 0.49})

    assert allowed is False
    assert reason == "blocked_by_recall_gate"


def test_should_run_direct_allows_at_recall_threshold():
    config = {"model_run": {"direct": {"enabled": True, "recall_gate": "block", "min_recall_at_5": 0.5}}}

    allowed, reason = should_run_direct(config, {"recall_at_5": 0.5})

    assert allowed is True
    assert reason == "enabled"


def test_model_response_key_dedupes_same_prompt_and_repeat():
    key1 = model_response_key("openai", "gpt-test", "direct", "q001", 0, "Prompt")
    key2 = model_response_key("openai", "gpt-test", "direct", "q001", 0, "Prompt")
    key3 = model_response_key("openai", "gpt-test", "direct", "q001", 1, "Prompt")

    assert key1 == key2
    assert key1 != key3


def test_evaluate_answer_rows_has_no_recall_gate():
    config = {
        "campaign": {
            "target_brand": "AlphaXXXX",
            "target_domain": "alphaxxxx.com",
            "competitors": ["Profound"],
        }
    }
    responses = [
        {
            "response_id": "resp_1",
            "query_id": "q001",
            "provider": "mock",
            "model": "mock-model",
            "mode": "direct",
            "repeat_index": 0,
            "raw_answer": "Profound is a known option. AlphaXXXX may also help. https://alphaxxxx.com/",
            "citations": ["https://alphaxxxx.com/"],
            "latency_ms": 10,
        }
    ]

    rows = evaluate_answer_rows(config, responses)

    assert rows[0]["brand_mentioned"] == "True"
    assert rows[0]["cited_own_url"] == "True"
    assert rows[0]["competitors_mentioned_json"] == json.dumps(["Profound"])


def test_provider_endpoint_supports_openrouter():
    endpoint = provider_endpoint({"provider": "openrouter"})

    assert endpoint == "https://openrouter.ai/api/v1/chat/completions"


def test_build_chat_payload_uses_clean_context_only():
    payload = build_chat_payload({"model": "openai/gpt-4.1-mini"}, "Prompt A", 0.2)

    assert payload["context_policy"] == "clean"
    assert payload["messages"] == [
        {
            "role": "system",
            "content": "You are a neutral research assistant evaluating vendors and sources.",
        },
        {"role": "user", "content": "Prompt A"},
    ]


def test_model_summary_rows_groups_metrics_by_llm():
    evaluations = [
        {
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
            "brand_mentioned": "True",
            "cited_own_url": "False",
            "recommended_own_brand": "True",
        },
        {
            "provider": "openrouter",
            "model": "openai/gpt-4.1-mini",
            "brand_mentioned": "False",
            "cited_own_url": "True",
            "recommended_own_brand": "False",
        },
    ]
    responses = [
        {"provider": "openrouter", "model": "openai/gpt-4.1-mini", "error": None},
        {"provider": "openrouter", "model": "openai/gpt-4.1-mini", "error": None},
        {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet", "error": "failed"},
    ]

    rows = model_summary_rows(evaluations, responses)

    assert rows[0]["model"] == "openai/gpt-4.1-mini"
    assert rows[0]["total_answers"] == 2
    assert rows[0]["brand_mention_rate"] == "50.0%"
    assert rows[0]["citation_rate"] == "50.0%"
    assert rows[1]["model"] == "anthropic/claude-3.5-sonnet"
    assert rows[1]["success_rate"] == "0.0%"


def test_build_summary_lists_configured_models_and_clean_context():
    config = {
        "campaign": {"target_brand": "AlphaXXXX"},
        "models": [
            {"provider": "openrouter", "model": "openai/gpt-4.1-mini"},
            {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet"},
        ],
    }
    rows = [
        {
            "query_id": "q001",
            "query": "best geo platform",
            "own_brand_rank": "",
            "own_brand_in_top_5": "False",
            "competitor_above_owned": "True",
            "matched_urls_json": "[]",
        }
    ]

    report = build_summary(config, rows)

    assert "openrouter/openai/gpt-4.1-mini" in report
    assert "openrouter/anthropic/claude-3.5-sonnet" in report
    assert "Context policy: clean per API call" in report
