import json
from collections import Counter
from pathlib import Path

from scripts.client_acquisition_simulator import (
    API_CALL_SUMMARY_FIELDS,
    IncrementalRunWriter,
    aggregate_brand_rows,
    build_orchestrator_from_config,
    build_api_call_summary,
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
from scripts.geo_eval.io import load_config


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


def test_generate_query_rows_can_use_orchestrator(tmp_path):
    class FakeOrchestrator:
        def __init__(self):
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            return {"raw_answer": json.dumps({"queries": ["How can my company get AI recommendations?"]})}

    orchestrator = FakeOrchestrator()
    rows, attempts = generate_query_rows(sample_config(tmp_path), orchestrator=orchestrator)

    assert rows[0]["query"] == "How can my company get AI recommendations?"
    assert attempts[0]["status"] == "success"
    assert orchestrator.calls[0]["task_type"] == "scenario_generation"
    assert orchestrator.calls[0]["prompt_version"] == "scenario_generation_v1"


def test_generate_query_rows_falls_back_and_records_error(tmp_path):
    def failing_caller(model_config, prompt, temperature):
        raise RuntimeError("api unavailable")

    rows, attempts = generate_query_rows(sample_config(tmp_path), caller=failing_caller)

    assert rows[0]["query"]
    assert rows[0]["api_status"] == "fallback"
    assert attempts[0]["status"] == "error"


def test_generate_query_rows_streams_each_scenario_batch(tmp_path):
    calls = {"count": 0}

    def interrupted_caller(model_config, prompt, temperature):
        calls["count"] += 1
        if calls["count"] == 2:
            raise KeyboardInterrupt()
        return {"raw_answer": json.dumps({"queries": ["How do I get recommended by ChatGPT?"]})}

    config = sample_config(tmp_path)
    config["client_acquisition"] = {
        "personas": ["p1"],
        "journey_stages": ["s1", "s2"],
        "queries_per_stage": 1,
    }
    writer = IncrementalRunWriter(tmp_path)

    try:
        generate_query_rows(config, caller=interrupted_caller, stream_writer=writer)
    except KeyboardInterrupt:
        pass

    assert "q001" in (tmp_path / "api_queries.csv").read_text(encoding="utf-8")
    assert "How do I get recommended by ChatGPT?" in (tmp_path / "api_queries.csv").read_text(encoding="utf-8")
    assert "scenario_generation" not in (tmp_path / "api_scenario_attempts.jsonl").read_text(encoding="utf-8")
    assert (tmp_path / "api_scenario_attempts.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_generate_query_rows_resumes_after_existing_scenario_slot(tmp_path):
    calls = {"count": 0}

    def fake_caller(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": json.dumps({"queries": ["Question for second slot"]})}

    config = sample_config(tmp_path)
    config["client_acquisition"] = {
        "personas": ["p1"],
        "journey_stages": ["s1", "s2"],
        "queries_per_stage": 1,
    }
    existing_rows = [
        {
            "query_id": "q001",
            "query": "Existing first slot question",
            "target_brand": "AlphaXXXX",
            "persona": "p1",
            "journey_stage": "s1",
            "scenario_provider": "openrouter",
            "scenario_model": "openai/gpt-4.1-mini",
            "api_status": "success",
            "notes": "already streamed",
        }
    ]

    rows, attempts = generate_query_rows(config, caller=fake_caller, existing_rows=existing_rows)

    assert calls["count"] == 1
    assert [row["query_id"] for row in rows] == ["q001", "q002"]
    assert rows[0]["query"] == "Existing first slot question"
    assert rows[1]["journey_stage"] == "s2"
    assert len(attempts) == 1


def test_generate_query_rows_does_not_generate_when_seeded_model_has_target_count(tmp_path):
    def fake_caller(model_config, prompt, temperature):
        raise AssertionError("seeded run should not regenerate scenarios")

    config = sample_config(tmp_path)
    config["client_acquisition"] = {
        "personas": ["p1"],
        "journey_stages": ["s1", "s2", "s3"],
        "queries_per_model": 3,
    }
    existing_rows = [
        {
            "query_id": f"q00{index}",
            "query": f"Seeded question {index}",
            "target_brand": "AlphaXXXX",
            "persona": "p1",
            "journey_stage": "s1",
            "scenario_provider": "openrouter",
            "scenario_model": "openai/gpt-4.1-mini",
            "api_status": "success",
            "notes": "seeded",
        }
        for index in range(1, 4)
    ]

    rows, attempts = generate_query_rows(config, caller=fake_caller, existing_rows=existing_rows)

    assert rows == existing_rows
    assert attempts == []


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


def test_rerank_candidates_can_use_orchestrator():
    class FakeOrchestrator:
        def __init__(self):
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            return {"raw_answer": '{"ranked_candidate_ids": ["c1"]}', "latency_ms": 7}

    orchestrator = FakeOrchestrator()
    rows, evidence, attempts = rerank_candidates(
        query_rows=[
            {
                "query_id": "q001",
                "query": "Question from model A",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-a",
            }
        ],
        candidates_by_query={"q001": [{"candidate_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com"}]},
        models=[{"provider": "openrouter", "model": "model-a"}],
        top_k=5,
        orchestrator=orchestrator,
    )

    assert rows[0]["winning_brand"] == "AlphaXXXX"
    assert attempts[0]["status"] == "success"
    assert orchestrator.calls[0]["task_type"] == "rerank"
    assert orchestrator.calls[0]["prompt_version"] == "rerank_v1"


def test_rerank_candidates_streams_rows_before_later_interrupt(tmp_path):
    calls = {"count": 0}

    def interrupted_caller(model_config, prompt, temperature):
        calls["count"] += 1
        if calls["count"] == 2:
            raise KeyboardInterrupt()
        return {"raw_answer": '{"ranked_candidate_ids": ["c1"]}', "latency_ms": 7}

    writer = IncrementalRunWriter(tmp_path)
    try:
        rerank_candidates(
            query_rows=[
                {
                    "query_id": "q001",
                    "query": "Question one",
                    "target_brand": "AlphaXXXX",
                    "scenario_provider": "openrouter",
                    "scenario_model": "model-a",
                },
                {
                    "query_id": "q002",
                    "query": "Question two",
                    "target_brand": "AlphaXXXX",
                    "scenario_provider": "openrouter",
                    "scenario_model": "model-a",
                },
            ],
            candidates_by_query={
                "q001": [{"candidate_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com"}],
                "q002": [{"candidate_id": "c1", "brand": "HornTech", "url": "https://horntech.com.au"}],
            },
            models=[{"provider": "openrouter", "model": "model-a"}],
            top_k=5,
            caller=interrupted_caller,
            stream_writer=writer,
        )
    except KeyboardInterrupt:
        pass

    assert (tmp_path / "retrieval_by_model.csv").read_text(encoding="utf-8").count("\n") == 2
    assert "q001" in (tmp_path / "retrieval_by_model.csv").read_text(encoding="utf-8")
    assert "q001" in (tmp_path / "retrieval_evidence_by_model.jsonl").read_text(encoding="utf-8")
    assert "q001" in (tmp_path / "api_rerank_attempts.jsonl").read_text(encoding="utf-8")


def test_rerank_candidates_skips_completed_keys_when_resuming(tmp_path):
    calls = {"count": 0}

    def fake_caller(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": '{"ranked_candidate_ids": ["c1"]}', "latency_ms": 7}

    writer = IncrementalRunWriter(tmp_path)
    rows, evidence, attempts = rerank_candidates(
        query_rows=[
            {
                "query_id": "q001",
                "query": "Already reranked",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-a",
            },
            {
                "query_id": "q002",
                "query": "Needs rerank",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-a",
            },
        ],
        candidates_by_query={
            "q001": [{"candidate_id": "c1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com"}],
            "q002": [{"candidate_id": "c1", "brand": "HornTech", "url": "https://horntech.com.au"}],
        },
        models=[{"provider": "openrouter", "model": "model-a"}],
        top_k=5,
        caller=fake_caller,
        stream_writer=writer,
        completed_keys={("openrouter", "model-a", "q001")},
    )

    assert calls["count"] == 1
    assert [row["query_id"] for row in rows] == ["q002"]
    assert [row["query_id"] for row in evidence] == ["q002"]
    assert [row["query_id"] for row in attempts] == ["q002"]
    output = (tmp_path / "retrieval_by_model.csv").read_text(encoding="utf-8")
    assert "q002" in output
    assert "q001" not in output


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


def test_build_answer_rows_can_use_orchestrator():
    class FakeOrchestrator:
        def __init__(self):
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            return {"raw_answer": "AlphaXXXX can help.", "latency_ms": 5}

    orchestrator = FakeOrchestrator()
    rows = build_answer_rows(
        query_rows=[
            {
                "query_id": "q001",
                "query": "Who can help?",
                "target_brand": "AlphaXXXX",
                "scenario_provider": "openrouter",
                "scenario_model": "model-a",
            }
        ],
        models=[{"provider": "openrouter", "model": "model-a"}],
        rerank_evidence=[
            {
                "query_id": "q001",
                "provider": "openrouter",
                "model": "model-a",
                "retrieved_chunks": [{"brand": "AlphaXXXX", "url": "https://alphaxxxx.com", "text_preview": "GEO agency"}],
            }
        ],
        orchestrator=orchestrator,
    )

    assert rows[0]["brand_mentioned"] == "True"
    assert orchestrator.calls[0]["task_type"] == "answer"
    assert orchestrator.calls[0]["prompt_version"] == "answer_v1"


def test_build_answer_rows_streams_rows_before_later_interrupt(tmp_path):
    calls = {"count": 0}

    def interrupted_caller(model_config, prompt, temperature):
        calls["count"] += 1
        if calls["count"] == 2:
            raise KeyboardInterrupt()
        return {"raw_answer": "AlphaXXXX can help.", "latency_ms": 5}

    writer = IncrementalRunWriter(tmp_path)
    try:
        build_answer_rows(
            query_rows=[
                {"query_id": "q001", "query": "Who can help?", "target_brand": "AlphaXXXX", "scenario_provider": "openrouter", "scenario_model": "model-a"},
                {"query_id": "q002", "query": "Who else can help?", "target_brand": "AlphaXXXX", "scenario_provider": "openrouter", "scenario_model": "model-a"},
            ],
            models=[{"provider": "openrouter", "model": "model-a"}],
            rerank_evidence=[
                {
                    "query_id": "q001",
                    "provider": "openrouter",
                    "model": "model-a",
                    "retrieved_chunks": [{"brand": "AlphaXXXX", "url": "https://alphaxxxx.com", "text_preview": "GEO agency"}],
                },
                {
                    "query_id": "q002",
                    "provider": "openrouter",
                    "model": "model-a",
                    "retrieved_chunks": [{"brand": "HornTech", "url": "https://horntech.com.au", "text_preview": "GEO agency"}],
                },
            ],
            caller=interrupted_caller,
            stream_writer=writer,
        )
    except KeyboardInterrupt:
        pass

    output = (tmp_path / "model_answer_evaluations.csv").read_text(encoding="utf-8")
    assert output.count("\n") == 2
    assert "q001" in output
    assert "q002" not in output


def test_build_answer_rows_skips_completed_keys_when_resuming(tmp_path):
    calls = {"count": 0}

    def fake_caller(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": "HornTech can help.", "latency_ms": 5}

    writer = IncrementalRunWriter(tmp_path)
    rows = build_answer_rows(
        query_rows=[
            {"query_id": "q001", "query": "Already answered", "target_brand": "AlphaXXXX", "scenario_provider": "openrouter", "scenario_model": "model-a"},
            {"query_id": "q002", "query": "Needs answer", "target_brand": "AlphaXXXX", "scenario_provider": "openrouter", "scenario_model": "model-a"},
        ],
        models=[{"provider": "openrouter", "model": "model-a"}],
        rerank_evidence=[
            {"query_id": "q001", "provider": "openrouter", "model": "model-a", "retrieved_chunks": []},
            {"query_id": "q002", "provider": "openrouter", "model": "model-a", "retrieved_chunks": []},
        ],
        caller=fake_caller,
        stream_writer=writer,
        completed_keys={("openrouter", "model-a", "q001")},
    )

    assert calls["count"] == 1
    assert [row["query_id"] for row in rows] == ["q002"]
    output = (tmp_path / "model_answer_evaluations.csv").read_text(encoding="utf-8")
    assert "q002" in output
    assert "q001" not in output


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


def test_aggregate_brand_rows_uses_query_count_for_mention_rate():
    rows = aggregate_brand_rows(
        [
            {
                "brand": "HornTech",
                "is_target": "False",
                "query_count": 200,
                "top5_count": 200,
                "top10_count": 200,
                "top10_slot_count": 1200,
                "best_rank": 1,
                "model_mention_count": 200,
                "top_urls_json": "[]",
            },
            {
                "brand": "HornTech",
                "is_target": "False",
                "query_count": 200,
                "top5_count": 200,
                "top10_count": 200,
                "top10_slot_count": 1200,
                "best_rank": 1,
                "model_mention_count": 200,
                "top_urls_json": "[]",
            },
        ]
    )

    assert rows[0]["model_mention_rate"] == "100.0%"


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


def test_full_config_contains_performance_pipeline_paths():
    config = load_config(Path("config/client_acquisition_simulator.yaml"))

    assert config["performance"]["llm_cache"]["enabled"] is True
    assert config["retrieval"]["hybrid"]["enabled"] is True
    assert config["retrieval"]["matrix"] == "config/intent_signal_matrix.yaml"
    assert config["retrieval"]["evidence_cards"] == "data/processed/evidence_cards.jsonl"


def test_build_orchestrator_from_config_respects_enabled_flag(tmp_path):
    config = sample_config(tmp_path)
    config["performance"] = {"llm_cache": {"enabled": False}}

    assert build_orchestrator_from_config(config, lambda model_config, prompt, temperature: {}) is None

    config["performance"] = {
        "llm_cache": {"enabled": True, "sqlite": str(tmp_path / "cache.sqlite")},
        "run_state": {"enabled": True, "sqlite": str(tmp_path / "state.sqlite")},
    }
    config["retrieval"] = {"matrix": "config/intent_signal_matrix.yaml"}
    orchestrator = build_orchestrator_from_config(config, lambda model_config, prompt, temperature: {})

    assert orchestrator is not None
    assert orchestrator.attempts_path.name == "api_orchestrator_attempts.jsonl"


def test_build_api_call_summary_groups_attempt_statuses():
    rows = build_api_call_summary(
        [
            {"task_type": "rerank", "provider": "openrouter", "model": "model-a", "status": "api_call", "cache_hit": False},
            {"task_type": "rerank", "provider": "openrouter", "model": "model-a", "status": "cache_hit", "cache_hit": True},
            {"task_type": "answer", "provider": "openrouter", "model": "model-a", "status": "error", "cache_hit": False},
        ]
    )

    assert API_CALL_SUMMARY_FIELDS == ["task_type", "provider", "model", "logical_calls", "api_calls", "cache_hits", "failures"]
    rerank = next(row for row in rows if row["task_type"] == "rerank")
    answer = next(row for row in rows if row["task_type"] == "answer")
    assert rerank["logical_calls"] == 2
    assert rerank["api_calls"] == 1
    assert rerank["cache_hits"] == 1
    assert answer["failures"] == 1


def test_competitive_gap_report_handles_empty_inputs():
    report = build_competitive_gap_report(
        target_brand="AlphaXXXX",
        brand_rows=[],
        retrieval_rows=[],
        retrieval_evidence=[],
        answer_rows=[],
        corpus_stats={},
    )

    assert "Competitive Gap Report" in report
