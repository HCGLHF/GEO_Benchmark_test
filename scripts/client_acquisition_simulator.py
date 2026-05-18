from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import stable_id, utc_now_iso
from scripts.eval_retrieval import calculate_retrieval_metrics, keyword_search
from scripts.geo_eval.io import load_config, write_jsonl
from scripts.geo_eval.models import call_chat_model
from scripts.geo_eval.orchestrator import ModelCallOrchestrator, canonical_hash


ChatCaller = Callable[[dict[str, Any], str, float], dict[str, Any]]


def path_content_hash(path: Path) -> str:
    if not path.exists():
        return canonical_hash({"missing": str(path)})
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_orchestrator_from_config(config: dict[str, Any], caller: ChatCaller = call_chat_model) -> ModelCallOrchestrator | None:
    performance = config.get("performance", {})
    llm_cache = performance.get("llm_cache", {})
    if not llm_cache.get("enabled", False):
        return None
    run_dir = Path(config.get("run", {}).get("output_dir", "runs/client_acquisition_simulator"))
    run_state = performance.get("run_state", {})
    retrieval = config.get("retrieval", {})
    matrix_path = Path(retrieval.get("matrix", "config/intent_signal_matrix.yaml"))
    documents_path = Path(retrieval.get("documents", "data/processed/documents.jsonl"))
    chunks_path = Path(retrieval.get("chunks", "data/processed/chunks.jsonl"))
    corpus_hash = canonical_hash(
        {
            "documents": path_content_hash(documents_path),
            "chunks": path_content_hash(chunks_path),
        }
    )
    return ModelCallOrchestrator(
        cache_path=Path(llm_cache.get("sqlite", "data/cache/llm_calls.sqlite")),
        run_state_path=Path(run_state.get("sqlite", run_dir / "run_state.sqlite")),
        attempts_path=run_dir / "api_orchestrator_attempts.jsonl",
        config_hash=canonical_hash(config),
        matrix_hash=path_content_hash(matrix_path),
        corpus_hash=corpus_hash,
        uncached_call=caller,
    )


QUERY_FIELDS = [
    "query_id",
    "query",
    "target_brand",
    "persona",
    "journey_stage",
    "scenario_provider",
    "scenario_model",
    "api_status",
    "notes",
]

RETRIEVAL_FIELDS = [
    "run_id",
    "query_id",
    "query",
    "provider",
    "model",
    "persona",
    "journey_stage",
    "top_k",
    "own_brand_rank",
    "own_brand_in_top_3",
    "own_brand_in_top_5",
    "own_brand_in_top_10",
    "winning_brand",
    "winning_source_type",
    "competitor_above_owned",
    "matched_urls_json",
]

ANSWER_FIELDS = [
    "query_id",
    "query",
    "provider",
    "model",
    "persona",
    "journey_stage",
    "raw_answer",
    "brand_mentioned",
    "recommended_own_brand",
    "latency_ms",
    "error",
]

BRAND_PERFORMANCE_FIELDS = [
    "provider",
    "model",
    "brand",
    "is_target",
    "query_count",
    "top1_count",
    "top5_count",
    "top10_count",
    "top10_slot_count",
    "top5_query_share",
    "top10_query_share",
    "best_rank",
    "average_best_rank",
    "model_mention_count",
    "model_mention_rate",
    "unique_url_count",
    "top_urls_json",
]

DIMENSION_FIELDS = [
    "dimension",
    "value",
    "query_count",
    "target_top5_count",
    "target_top5_share",
    "leading_winner",
    "winner_count",
]

API_CALL_SUMMARY_FIELDS = ["task_type", "provider", "model", "logical_calls", "api_calls", "cache_hits", "failures"]


def pct(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator if denominator else 0.0):.1%}"


def parse_percent(value: Any) -> float:
    text = str(value or "0").strip().removesuffix("%")
    try:
        return float(text) / 100
    except ValueError:
        return 0.0


def is_true(value: Any) -> bool:
    return str(value).lower() == "true"


def default_scenario_matrix(config: dict[str, Any]) -> dict[str, Any]:
    client_config = config.get("client_acquisition", {})
    return {
        "personas": client_config.get("personas")
        or ["SaaS founder", "SEO agency owner", "local business owner"],
        "journey_stages": client_config.get("journey_stages")
        or [
            "problem_aware",
            "solution_aware",
            "vendor_discovery",
            "trust_validation",
            "objection_handling",
        ],
        "queries_per_stage": int(client_config.get("queries_per_stage", 1)),
        "queries_per_model": int(client_config["queries_per_model"]) if client_config.get("queries_per_model") else None,
    }


def scenario_counts_for_model(matrix: dict[str, Any]) -> list[tuple[str, str, int]]:
    slots = [(persona, stage) for persona in matrix["personas"] for stage in matrix["journey_stages"]]
    queries_per_model = matrix.get("queries_per_model")
    if not queries_per_model:
        return [(persona, stage, int(matrix["queries_per_stage"])) for persona, stage in slots]
    base_count, remainder = divmod(int(queries_per_model), len(slots))
    return [
        (persona, stage, base_count + (1 if index < remainder else 0))
        for index, (persona, stage) in enumerate(slots)
    ]


def parse_json_object(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw_text[start : end + 1])
    return {}


def sanitize_model_text(text: str) -> str:
    replacements = {
        "閳ユ獨": "'s",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        "â€‘": "-",
    }
    for broken, fixed in replacements.items():
        text = text.replace(broken, fixed)
    return text


def build_scenario_prompt(config: dict[str, Any], persona: str, journey_stage: str, count: int) -> str:
    campaign = config.get("campaign", {})
    return (
        "Generate realistic search or AI-chat queries from potential clients looking for GEO services. "
        "GEO means Generative Engine Optimization, AI search visibility, and getting a brand recommended "
        "or cited by AI systems. Return strict JSON only with this shape: "
        '{"queries":["question 1","question 2"]}.\n\n'
        f"Target brand: {campaign.get('target_brand', '')}\n"
        f"Market: {campaign.get('market', '')}\n"
        f"Service category: {campaign.get('category', '')}\n"
        f"Persona: {persona}\n"
        f"Customer journey stage: {journey_stage}\n"
        f"Number of queries: {count}\n"
        "Use natural client language, include vague/problem-led wording where appropriate, and do not force the target brand name. "
        "Use plain ASCII punctuation."
    )


def fallback_query(config: dict[str, Any], persona: str, journey_stage: str) -> str:
    market = config.get("campaign", {}).get("market", "Australia")
    if journey_stage == "problem_aware":
        return f"Why are my competitors showing up in ChatGPT but my company is not in {market}?"
    if journey_stage == "vendor_discovery":
        return f"Who can help a {persona} get recommended by ChatGPT and Perplexity in {market}?"
    if journey_stage == "trust_validation":
        return f"What proof should I look for before hiring a GEO agency in {market}?"
    if journey_stage == "objection_handling":
        return "Can a GEO agency really help my company get recommended by AI?"
    return f"How can a {persona} improve AI search visibility in {market}?"


def generate_query_rows(
    config: dict[str, Any],
    caller: ChatCaller = call_chat_model,
    orchestrator: Any | None = None,
    stream_writer: Any | None = None,
    existing_rows: list[dict[str, Any]] | None = None,
    existing_attempts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matrix = default_scenario_matrix(config)
    target_brand = str(config.get("campaign", {}).get("target_brand", ""))
    models = config.get("models", [])
    rows: list[dict[str, Any]] = list(existing_rows or [])
    attempts: list[dict[str, Any]] = list(existing_attempts or [])
    query_index = next_query_index(rows)
    for model_config in models:
        provider = str(model_config.get("provider", ""))
        model = str(model_config.get("model", ""))
        for persona, stage, query_count in scenario_counts_for_model(matrix):
            existing_slot_count = sum(
                1
                for row in rows
                if str(row.get("scenario_provider", "")) == provider
                and str(row.get("scenario_model", "")) == model
                and str(row.get("persona", "")) == persona
                and str(row.get("journey_stage", "")) == stage
            )
            missing_query_count = max(query_count - existing_slot_count, 0)
            if missing_query_count == 0:
                continue
            prompt = build_scenario_prompt(config, persona, stage, missing_query_count)
            attempt = {
                "provider": provider,
                "model": model,
                "persona": persona,
                "journey_stage": stage,
                "used_api": True,
                "status": "success",
                "error": None,
                "requested_query_count": missing_query_count,
                "created_at": utc_now_iso(),
            }
            try:
                temperature = float(config.get("model_run", {}).get("temperature", 0.2))
                if orchestrator:
                    result = orchestrator.call(
                        model_config=model_config,
                        prompt=prompt,
                        temperature=temperature,
                        task_type="scenario_generation",
                        query_id=f"scenario:{provider}:{model}:{persona}:{stage}",
                        input_hash=canonical_hash({"persona": persona, "journey_stage": stage, "query_count": missing_query_count}),
                        prompt_version="scenario_generation_v1",
                    )
                else:
                    result = caller(model_config, prompt, temperature)
                parsed = parse_json_object(str(result.get("raw_answer", "")))
                queries = [sanitize_model_text(str(item).strip()) for item in parsed.get("queries", []) if str(item).strip()]
                if not queries:
                    raise ValueError("API response did not include queries")
            except Exception as exc:
                queries = [fallback_query(config, persona, stage)]
                attempt["status"] = "error"
                attempt["error"] = str(exc)
            attempts.append(attempt)
            for query in queries[:missing_query_count]:
                rows.append(
                    row := {
                        "query_id": f"q{query_index:03d}",
                        "query": query,
                        "target_brand": target_brand,
                        "persona": persona,
                        "journey_stage": stage,
                        "scenario_provider": provider,
                        "scenario_model": model,
                        "api_status": "success" if attempt["status"] == "success" else "fallback",
                        "notes": "API-generated client acquisition query" if attempt["status"] == "success" else "Fallback query after API error",
                    }
                )
                if stream_writer:
                    stream_writer.write_query(row)
                query_index += 1
            if stream_writer:
                stream_writer.write_scenario_attempt(attempt)
    return rows, attempts


def build_rerank_prompt(query: str, candidates: list[dict[str, Any]], top_k: int) -> str:
    compact = [
        {
            "candidate_id": item["candidate_id"],
            "brand": item.get("brand"),
            "url": item.get("url"),
            "title": item.get("title"),
            "source_type": item.get("source_type"),
            "text_preview": str(item.get("text", ""))[:700],
        }
        for item in candidates
    ]
    return (
        "You are simulating which pages an AI search system would use to answer a potential client's GEO service question. "
        "Rank the candidates by usefulness, trust, service fit, and likelihood of supporting a recommendation. "
        "Return strict JSON only with this shape: "
        '{"ranked_candidate_ids":["c1","c2"],"reasons":{"c1":"short reason"}}.\n\n'
        f"Question: {query}\n"
        f"Return up to {top_k} ranked candidate ids, but include all useful candidates if possible.\n"
        f"Candidates JSON:\n{json.dumps(compact, ensure_ascii=False)}"
    )


def parse_rerank_response(raw_text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = parse_json_object(raw_text)
    requested_ids = [str(item) for item in parsed.get("ranked_candidate_ids", [])]
    by_id = {str(item["candidate_id"]): item for item in candidates}
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    reasons = parsed.get("reasons", {}) if isinstance(parsed.get("reasons", {}), dict) else {}
    for candidate_id in requested_ids:
        if candidate_id in by_id and candidate_id not in seen:
            ranked.append(by_id[candidate_id] | {"rerank_reason": reasons.get(candidate_id, "")})
            seen.add(candidate_id)
    for item in candidates:
        candidate_id = str(item["candidate_id"])
        if candidate_id not in seen:
            ranked.append(item | {"rerank_reason": ""})
    return ranked


def query_matches_model(query: dict[str, Any], provider: str, model: str) -> bool:
    scenario_provider = str(query.get("scenario_provider", ""))
    scenario_model = str(query.get("scenario_model", ""))
    if not scenario_provider and not scenario_model:
        return True
    return scenario_provider == provider and scenario_model == model


def next_query_index(rows: list[dict[str, Any]]) -> int:
    largest = 0
    for row in rows:
        query_id = str(row.get("query_id", ""))
        if query_id.startswith("q") and query_id[1:].isdigit():
            largest = max(largest, int(query_id[1:]))
    return largest + 1


def result_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("provider", "")), str(row.get("model", "")), str(row.get("query_id", "")))


def rerank_candidates(
    query_rows: list[dict[str, Any]],
    candidates_by_query: dict[str, list[dict[str, Any]]],
    models: list[dict[str, Any]],
    top_k: int,
    caller: ChatCaller = call_chat_model,
    orchestrator: Any | None = None,
    stream_writer: Any | None = None,
    completed_keys: set[tuple[str, str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metric_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    run_id = stable_id("run", f"client-acquisition:{len(query_rows)}:{top_k}:{utc_now_iso()}")
    for model_config in models:
        provider = str(model_config.get("provider", ""))
        model = str(model_config.get("model", ""))
        for query in query_rows:
            if not query_matches_model(query, provider, model):
                continue
            if completed_keys and (provider, model, str(query["query_id"])) in completed_keys:
                continue
            candidates = candidates_by_query.get(str(query["query_id"]), [])
            prompt = build_rerank_prompt(str(query["query"]), candidates, top_k)
            attempt = {
                "query_id": query["query_id"],
                "provider": provider,
                "model": model,
                "used_api": True,
                "status": "success",
                "error": None,
                "created_at": utc_now_iso(),
            }
            try:
                if orchestrator:
                    result = orchestrator.call(
                        model_config=model_config,
                        prompt=prompt,
                        temperature=0,
                        task_type="rerank",
                        query_id=str(query["query_id"]),
                        input_hash=canonical_hash(
                            {
                                "query_id": query["query_id"],
                                "query": query["query"],
                                "top_k": top_k,
                                "candidates": [
                                    {
                                        "candidate_id": item.get("candidate_id"),
                                        "url": item.get("url"),
                                        "brand": item.get("brand"),
                                        "title": item.get("title"),
                                        "text": str(item.get("text", ""))[:700],
                                    }
                                    for item in candidates
                                ],
                            }
                        ),
                        prompt_version="rerank_v1",
                    )
                else:
                    result = caller(model_config, prompt, 0)
                ranked = parse_rerank_response(sanitize_model_text(str(result.get("raw_answer", ""))), candidates)
            except Exception as exc:
                ranked = list(candidates)
                attempt["status"] = "error"
                attempt["error"] = str(exc)
            attempts.append(attempt)
            record = calculate_retrieval_metrics(
                query_id=str(query["query_id"]),
                query=str(query["query"]),
                target_brand=str(query.get("target_brand", "")),
                results=ranked,
                top_k=top_k,
                run_id=run_id,
            )
            data = record.model_dump()
            metric_row = {
                "run_id": data["run_id"],
                "query_id": data["query_id"],
                "query": data["query"],
                "provider": provider,
                "model": model,
                "persona": query.get("persona", ""),
                "journey_stage": query.get("journey_stage", ""),
                "top_k": data["top_k"],
                "own_brand_rank": data["own_brand_rank"],
                "own_brand_in_top_3": data["own_brand_in_top_3"],
                "own_brand_in_top_5": data["own_brand_in_top_5"],
                "own_brand_in_top_10": data["own_brand_in_top_10"],
                "winning_brand": data["winning_brand"],
                "winning_source_type": data["winning_source_type"],
                "competitor_above_owned": data["competitor_above_owned"],
                "matched_urls_json": data["matched_urls_json"],
            }
            evidence_row = {
                "query_id": query["query_id"],
                "query": query["query"],
                "provider": provider,
                "model": model,
                "persona": query.get("persona", ""),
                "journey_stage": query.get("journey_stage", ""),
                "retrieved_chunks": [
                    {
                        "candidate_id": item.get("candidate_id"),
                        "chunk_id": item.get("chunk_id"),
                        "brand": item.get("brand"),
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "source_type": item.get("source_type"),
                        "rerank_reason": item.get("rerank_reason", ""),
                        "text_preview": str(item.get("text", ""))[:700],
                    }
                    for item in ranked[:top_k]
                ],
            }
            metric_rows.append(metric_row)
            evidence_rows.append(evidence_row)
            if stream_writer:
                stream_writer.write_rerank(metric_row, evidence_row, attempt)
    return metric_rows, evidence_rows, attempts


def build_answer_prompt(query: str, evidence: dict[str, Any]) -> str:
    context = "\n\n".join(
        f"Brand: {chunk.get('brand')}\nURL: {chunk.get('url')}\nText: {chunk.get('text_preview', '')}"
        for chunk in evidence.get("retrieved_chunks", [])[:5]
    )
    return (
        "You are simulating an AI assistant answering a potential client who is considering GEO services. "
        "Answer naturally, recommend practical options if appropriate, and cite URLs from the supplied context when useful. "
        "If the context does not support a recommendation, say what information is missing.\n\n"
        f"Client question: {query}\n\nContext:\n{context}"
    )


def build_answer_rows(
    query_rows: list[dict[str, Any]],
    models: list[dict[str, Any]],
    rerank_evidence: list[dict[str, Any]],
    caller: ChatCaller = call_chat_model,
    orchestrator: Any | None = None,
    stream_writer: Any | None = None,
    completed_keys: set[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    query_by_id = {row["query_id"]: row for row in query_rows}
    evidence_by_key = {(row["provider"], row["model"], row["query_id"]): row for row in rerank_evidence}
    rows: list[dict[str, Any]] = []
    for model_config in models:
        provider = str(model_config.get("provider", ""))
        model = str(model_config.get("model", ""))
        for query in query_rows:
            if not query_matches_model(query, provider, model):
                continue
            if completed_keys and (provider, model, str(query["query_id"])) in completed_keys:
                continue
            evidence = evidence_by_key.get((provider, model, query["query_id"]), {})
            prompt = build_answer_prompt(str(query["query"]), evidence)
            error = None
            latency_ms = None
            answer = ""
            try:
                if orchestrator:
                    result = orchestrator.call(
                        model_config=model_config,
                        prompt=prompt,
                        temperature=0.2,
                        task_type="answer",
                        query_id=str(query["query_id"]),
                        input_hash=canonical_hash(
                            {
                                "query_id": query["query_id"],
                                "query": query["query"],
                                "evidence": evidence.get("retrieved_chunks", [])[:5],
                            }
                        ),
                        prompt_version="answer_v1",
                    )
                else:
                    result = caller(model_config, prompt, 0.2)
                answer = sanitize_model_text(str(result.get("raw_answer", "")))
                latency_ms = result.get("latency_ms")
            except Exception as exc:
                error = str(exc)
            target_brand = str(query.get("target_brand", ""))
            answer_lower = answer.lower()
            brand_mentioned = bool(target_brand and target_brand.lower() in answer_lower)
            answer_row = {
                "query_id": query["query_id"],
                "query": query["query"],
                "provider": provider,
                "model": model,
                "persona": query_by_id[query["query_id"]].get("persona", ""),
                "journey_stage": query_by_id[query["query_id"]].get("journey_stage", ""),
                "raw_answer": answer,
                "brand_mentioned": str(brand_mentioned),
                "recommended_own_brand": str(brand_mentioned and "recommend" in answer_lower),
                "latency_ms": latency_ms,
                "error": error,
            }
            rows.append(answer_row)
            if stream_writer:
                stream_writer.write_answer(answer_row)
    return rows


def build_brand_performance_by_model(
    target_brand: str,
    configured_brands: list[str],
    retrieval_evidence: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_by_model: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    answers_by_model: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    brands = {target_brand, *configured_brands}
    for row in retrieval_evidence:
        key = (str(row.get("provider", "")), str(row.get("model", "")))
        evidence_by_model[key].append(row)
        for rank, chunk in enumerate(row.get("retrieved_chunks", []), start=1):
            if chunk.get("brand"):
                brands.add(str(chunk["brand"]))
    for row in answer_rows:
        answers_by_model[(str(row.get("provider", "")), str(row.get("model", "")))].append(row)

    rows: list[dict[str, Any]] = []
    for key in sorted(set(evidence_by_model.keys()) | set(answers_by_model.keys())):
        provider, model = key
        evidence_rows = evidence_by_model.get(key, [])
        answer_group = [row for row in answers_by_model.get(key, []) if not row.get("error")]
        query_count = len({row.get("query_id") for row in evidence_rows})
        ranks_by_brand: dict[str, list[int]] = defaultdict(list)
        urls_by_brand: dict[str, Counter[str]] = defaultdict(Counter)
        for evidence in evidence_rows:
            seen_query_brand: set[tuple[str, str]] = set()
            for rank, chunk in enumerate(evidence.get("retrieved_chunks", []), start=1):
                brand = str(chunk.get("brand") or "Unknown")
                url = str(chunk.get("url") or "")
                ranks_by_brand[brand].append(rank)
                if url and (brand, url) not in seen_query_brand:
                    urls_by_brand[brand][url] += 1
                    seen_query_brand.add((brand, url))
        for brand in sorted(brands, key=lambda item: (item != target_brand, item.lower())):
            ranks = ranks_by_brand.get(brand, [])
            top1 = sum(1 for rank in ranks if rank == 1)
            top5 = min(sum(1 for rank in ranks if rank <= 5), query_count)
            top10 = min(sum(1 for rank in ranks if rank <= 10), query_count)
            mention_count = sum(1 for row in answer_group if brand.lower() in str(row.get("raw_answer", "")).lower())
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "brand": brand,
                    "is_target": str(brand == target_brand),
                    "query_count": query_count,
                    "top1_count": top1,
                    "top5_count": top5,
                    "top10_count": top10,
                    "top10_slot_count": len(ranks),
                    "top5_query_share": pct(top5, query_count),
                    "top10_query_share": pct(top10, query_count),
                    "best_rank": min(ranks) if ranks else "",
                    "average_best_rank": f"{sum(ranks) / len(ranks):.2f}" if ranks else "",
                    "model_mention_count": mention_count,
                    "model_mention_rate": pct(mention_count, len(answer_group)),
                    "unique_url_count": len(urls_by_brand.get(brand, {})),
                    "top_urls_json": json.dumps([url for url, _count in urls_by_brand.get(brand, Counter()).most_common(5)], ensure_ascii=False),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["model"],
            row["is_target"] != "True",
            -int(row["top5_count"]),
            -int(row["top10_slot_count"]),
            str(row["brand"]).lower(),
        ),
    )


def load_corpus_stats(documents_path: Path = Path("data/processed/documents.jsonl"), chunks_path: Path = Path("data/processed/chunks.jsonl")) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"document_count": 0, "chunk_count": 0, "url_count": 0})
    urls_by_brand: dict[str, set[str]] = defaultdict(set)
    if documents_path.exists():
        with documents_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                brand = str(row.get("brand") or "Unknown")
                stats[brand]["document_count"] += 1
                if row.get("url"):
                    urls_by_brand[brand].add(str(row["url"]))
    if chunks_path.exists():
        with chunks_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                brand = str(row.get("brand") or "Unknown")
                stats[brand]["chunk_count"] += 1
    for brand, urls in urls_by_brand.items():
        stats[brand]["url_count"] = len(urls)
    return dict(stats)


def build_dimension_breakdown(retrieval_rows: list[dict[str, Any]], target_brand: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dimensions = {
        "model": lambda row: str(row.get("model", "")),
        "persona": lambda row: str(row.get("persona", "")),
        "journey_stage": lambda row: str(row.get("journey_stage", "")),
    }
    for dimension, getter in dimensions.items():
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in retrieval_rows:
            groups[getter(row)].append(row)
        for value, group in sorted(groups.items()):
            winner_counts = Counter(str(row.get("winning_brand") or "Unknown") for row in group)
            leading_winner, winner_count = winner_counts.most_common(1)[0] if winner_counts else ("", 0)
            top5_count = sum(is_true(row.get("own_brand_in_top_5")) for row in group)
            rows.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "query_count": len(group),
                    "target_top5_count": top5_count,
                    "target_top5_share": pct(top5_count, len(group)),
                    "leading_winner": leading_winner if leading_winner != target_brand else target_brand,
                    "winner_count": winner_count,
                }
            )
    return rows


def aggregate_brand_rows(brand_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in brand_rows:
        grouped[str(row.get("brand", ""))].append(row)
    aggregated: list[dict[str, Any]] = []
    for brand, rows in grouped.items():
        top5_slots = sum(int(row.get("top5_count") or 0) for row in rows)
        top10_slots = sum(int(row.get("top10_count") or 0) for row in rows)
        top10_slot_count = sum(int(row.get("top10_slot_count") or 0) for row in rows)
        query_count = sum(int(row.get("query_count") or 0) for row in rows)
        mention_count = sum(int(row.get("model_mention_count") or 0) for row in rows)
        ranks = [int(row["best_rank"]) for row in rows if str(row.get("best_rank", "")).isdigit()]
        urls: list[str] = []
        for row in rows:
            try:
                urls.extend(json.loads(row.get("top_urls_json") or "[]"))
            except json.JSONDecodeError:
                pass
        aggregated.append(
            {
                "brand": brand,
                "is_target": rows[0].get("is_target", "False"),
                "model_count": len(rows),
                "query_count": query_count,
                "top5_query_share": pct(top5_slots, query_count),
                "top10_query_share": pct(top10_slots, query_count),
                "top10_slot_count": top10_slot_count,
                "best_rank": min(ranks) if ranks else "",
                "model_mention_rate": pct(mention_count, query_count),
                "top_urls": list(dict.fromkeys(urls))[:5],
            }
        )
    return sorted(
        aggregated,
        key=lambda row: (
            row["is_target"] != "True",
            -parse_percent(row["top5_query_share"]),
            -int(row["top10_slot_count"]),
            str(row["brand"]).lower(),
        ),
    )


def content_gap_signals(
    target_brand: str,
    retrieval_evidence: list[dict[str, Any]],
    limit: int = 8,
    brand_filter: str | None = None,
) -> list[str]:
    phrases = Counter()
    phrase_labels = {
        "custom ai development services": "custom AI development services",
        "ai development services": "AI development services",
        "workflow automation": "workflow automation",
        "ai visibility toolkit": "AI visibility toolkit",
        "marketing teams": "marketing teams",
        "pricing": "pricing",
        "case study": "case study",
        "free audit": "free audit",
        "australia": "Australia",
        "sydney": "Sydney",
        "chatgpt": "ChatGPT",
        "perplexity": "Perplexity",
        "ai overviews": "AI Overviews",
        "get found in ai search engines": "get found in AI search engines",
        "brand visibility tool": "brand visibility tool",
        "customer examples": "customer examples",
    }
    for evidence in retrieval_evidence:
        for chunk in evidence.get("retrieved_chunks", [])[:5]:
            brand = str(chunk.get("brand") or "")
            if brand == target_brand:
                continue
            if brand_filter and brand != brand_filter:
                continue
            text = f"{chunk.get('title', '')} {chunk.get('text_preview', '')}".lower()
            for phrase in phrase_labels:
                if phrase in text:
                    phrases[phrase] += 1
    return [phrase_labels[phrase] for phrase, _count in phrases.most_common(limit)]


def build_competitive_gap_report(
    target_brand: str,
    brand_rows: list[dict[str, Any]],
    retrieval_rows: list[dict[str, Any]],
    retrieval_evidence: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
    corpus_stats: dict[str, dict[str, int]],
) -> str:
    aggregated = aggregate_brand_rows(brand_rows)
    target = next((row for row in aggregated if row["brand"] == target_brand), None)
    target_top5 = parse_percent(target["top5_query_share"]) if target else 0.0
    target_mentions = parse_percent(target["model_mention_rate"]) if target else 0.0
    above_target = [
        row
        for row in aggregated
        if row["brand"] != target_brand
        and (parse_percent(row["top5_query_share"]) > target_top5 or parse_percent(row["model_mention_rate"]) > target_mentions)
    ]
    dimensions = build_dimension_breakdown(retrieval_rows, target_brand)
    gaps = content_gap_signals(target_brand, retrieval_evidence)
    successful_answers = [row for row in answer_rows if not row.get("error")]
    target_corpus = corpus_stats.get(target_brand, {"document_count": 0, "chunk_count": 0, "url_count": 0})

    lines = [
        f"# Competitive Gap Report: {target_brand}",
        "",
        "## Target Snapshot",
        "",
        f"- Corpus URLs: {target_corpus.get('url_count', 0)}",
        f"- Corpus documents: {target_corpus.get('document_count', 0)}",
        f"- Corpus chunks: {target_corpus.get('chunk_count', 0)}",
        f"- Successful model answers: {len(successful_answers)}",
    ]
    if target:
        lines.extend(
            [
                f"- Retrieval Top5 share: {target['top5_query_share']}",
                f"- Retrieval Top10 share: {target['top10_query_share']}",
                f"- Best rank: {target['best_rank'] or 'not ranked'}",
                f"- Model mention rate: {target['model_mention_rate']}",
            ]
        )
    else:
        lines.append("- Target brand did not appear in retrieval or answer metrics.")

    lines.extend(["", f"## Brands Above {target_brand}", "", "| Brand | Top5 Share | Top10 Share | Top10 Slots | Best Rank | Model Mention | Corpus URLs | Top URLs |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
    if above_target:
        for row in above_target[:15]:
            stats = corpus_stats.get(row["brand"], {})
            top_urls = "<br>".join(row.get("top_urls", [])[:3])
            lines.append(
                f"| {row['brand']} | {row['top5_query_share']} | {row['top10_query_share']} | "
                f"{row['top10_slot_count']} | {row['best_rank'] or 'not ranked'} | {row['model_mention_rate']} | "
                f"{stats.get('url_count', 0)} | {top_urls} |"
            )
    else:
        lines.append(f"| No brand is currently above {target_brand}. |  |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Likely Gaps vs Winners",
            "",
            "| Brand | Corpus Gap | Retrieval Advantage | Likely Missing Signals |",
            "| --- | --- | --- | --- |",
        ]
    )
    if above_target:
        for row in above_target[:10]:
            stats = corpus_stats.get(row["brand"], {})
            url_gap = int(stats.get("url_count", 0)) - int(target_corpus.get("url_count", 0))
            chunk_gap = int(stats.get("chunk_count", 0)) - int(target_corpus.get("chunk_count", 0))
            gap_text = f"{max(url_gap, 0)} more URLs, {max(chunk_gap, 0)} more chunks"
            advantage = f"Top5 {row['top5_query_share']}, mention {row['model_mention_rate']}, best rank {row['best_rank'] or 'not ranked'}"
            signals = ", ".join(content_gap_signals(target_brand, retrieval_evidence, limit=5, brand_filter=row["brand"]))
            lines.append(f"| {row['brand']} | {gap_text} | {advantage} | {signals or 'No repeated signal detected'} |")
    else:
        lines.append(f"| {target_brand} | No stronger winner detected in this run. |  |  |")

    lines.extend(["", "## Weak Dimensions", "", "| Dimension | Value | Queries | Target Top5 | Leading Winner | Winner Count |", "| --- | --- | ---: | ---: | --- | ---: |"])
    for row in dimensions:
        lines.append(
            f"| {row['dimension']} | {row['value']} | {row['query_count']} | "
            f"{row['target_top5_share']} | {row['leading_winner']} | {row['winner_count']} |"
        )

    lines.extend(["", "## Content Gap Signals", ""])
    if gaps:
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- No recurring competitor content signals were detected from the current run.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- If a competitor appears above {target_brand}, it means at least one model ranked that competitor's page higher or mentioned that competitor more often in final answers.",
            "- Content gap signals are extracted from competitor pages that models selected into Top5; they are directional, not proof of causality.",
            "- A low target score with a low corpus URL count usually means both content depth and intent-specific landing pages should be expanded.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def append_csv_rows(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def append_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class IncrementalRunWriter:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)

    def reset_stage_outputs(self, stage: str) -> None:
        groups = {
            "scenario": ["api_queries.csv", "api_scenario_attempts.jsonl"],
            "rerank": ["retrieval_by_model.csv", "retrieval_evidence_by_model.jsonl", "api_rerank_attempts.jsonl"],
            "answer": ["model_answer_evaluations.csv"],
        }
        for filename in groups.get(stage, []):
            path = self.run_dir / filename
            if path.exists():
                path.unlink()

    def write_query(self, row: dict[str, Any]) -> None:
        append_csv_rows(self.run_dir / "api_queries.csv", [row], QUERY_FIELDS)

    def write_scenario_attempt(self, row: dict[str, Any]) -> None:
        append_jsonl_rows(self.run_dir / "api_scenario_attempts.jsonl", [row])

    def write_rerank(self, metric_row: dict[str, Any], evidence_row: dict[str, Any], attempt_row: dict[str, Any]) -> None:
        append_csv_rows(self.run_dir / "retrieval_by_model.csv", [metric_row], RETRIEVAL_FIELDS)
        append_jsonl_rows(self.run_dir / "retrieval_evidence_by_model.jsonl", [evidence_row])
        append_jsonl_rows(self.run_dir / "api_rerank_attempts.jsonl", [attempt_row])

    def write_answer(self, row: dict[str, Any]) -> None:
        append_csv_rows(self.run_dir / "model_answer_evaluations.csv", [row], ANSWER_FIELDS)


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_api_call_summary(attempt_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in attempt_rows:
        key = (str(row.get("task_type", "")), str(row.get("provider", "")), str(row.get("model", "")))
        grouped[key].append(row)
    summary = []
    for (task_type, provider, model), rows in sorted(grouped.items()):
        summary.append(
            {
                "task_type": task_type,
                "provider": provider,
                "model": model,
                "logical_calls": len(rows),
                "api_calls": sum(1 for row in rows if row.get("status") == "api_call"),
                "cache_hits": sum(1 for row in rows if row.get("status") == "cache_hit" or str(row.get("cache_hit")).lower() == "true"),
                "failures": sum(1 for row in rows if row.get("status") == "error"),
            }
        )
    return summary


def candidate_recall(config: dict[str, Any], query_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    with Path(config.get("retrieval", {}).get("keyword_index", "data/processed/bm25_index.pkl")).open("rb") as handle:
        artifact = pickle.load(handle)
    pool_size = int(config.get("run", {}).get("candidate_pool_size", 30))
    hybrid_enabled = bool(config.get("retrieval", {}).get("hybrid", {}).get("enabled", False))
    candidates_by_query: dict[str, list[dict[str, Any]]] = {}
    for query in query_rows:
        bm25_candidates = keyword_search(str(query["query"]), artifact, pool_size)
        if hybrid_enabled:
            from scripts.geo_eval.hybrid_recall import fuse_candidate_lists

            candidates = fuse_candidate_lists({"bm25": bm25_candidates}, top_n=pool_size)
        else:
            candidates = bm25_candidates
        candidates_by_query[str(query["query_id"])] = [
            candidate | {"candidate_id": f"c{index:03d}"}
            for index, candidate in enumerate(candidates, start=1)
        ]
    return candidates_by_query


def run_simulator(config: dict[str, Any], caller: ChatCaller = call_chat_model) -> dict[str, Any]:
    run_dir = Path(config.get("run", {}).get("output_dir", "runs/client_acquisition_simulator"))
    top_k = int(config.get("run", {}).get("top_k", 10))
    models = config.get("models", [])
    orchestrator = build_orchestrator_from_config(config, caller=caller)
    stream_writer = IncrementalRunWriter(run_dir)
    existing_query_rows = read_csv_rows(run_dir / "api_queries.csv")
    existing_scenario_attempts = read_jsonl_rows(run_dir / "api_scenario_attempts.jsonl")
    if not existing_query_rows and not existing_scenario_attempts:
        stream_writer.reset_stage_outputs("scenario")
    query_rows, scenario_attempts = generate_query_rows(
        config,
        caller=caller,
        orchestrator=orchestrator,
        stream_writer=stream_writer,
        existing_rows=existing_query_rows,
        existing_attempts=existing_scenario_attempts,
    )
    write_csv(run_dir / "api_queries.csv", query_rows, QUERY_FIELDS)
    write_jsonl(run_dir / "api_scenario_attempts.jsonl", scenario_attempts)

    candidates_by_query = candidate_recall(config, query_rows)
    existing_retrieval_rows = read_csv_rows(run_dir / "retrieval_by_model.csv")
    existing_retrieval_evidence = read_jsonl_rows(run_dir / "retrieval_evidence_by_model.jsonl")
    existing_rerank_attempts = read_jsonl_rows(run_dir / "api_rerank_attempts.jsonl")
    if not existing_retrieval_rows and not existing_retrieval_evidence and not existing_rerank_attempts:
        stream_writer.reset_stage_outputs("rerank")
    new_retrieval_rows, new_retrieval_evidence, new_rerank_attempts = rerank_candidates(
        query_rows=query_rows,
        candidates_by_query=candidates_by_query,
        models=models,
        top_k=top_k,
        caller=caller,
        orchestrator=orchestrator,
        stream_writer=stream_writer,
        completed_keys={result_key(row) for row in existing_retrieval_rows},
    )
    retrieval_rows = existing_retrieval_rows + new_retrieval_rows
    retrieval_evidence = existing_retrieval_evidence + new_retrieval_evidence
    rerank_attempts = existing_rerank_attempts + new_rerank_attempts
    write_csv(run_dir / "retrieval_by_model.csv", retrieval_rows, RETRIEVAL_FIELDS)
    write_jsonl(run_dir / "retrieval_evidence_by_model.jsonl", retrieval_evidence)
    write_jsonl(run_dir / "api_rerank_attempts.jsonl", rerank_attempts)

    existing_answer_rows = read_csv_rows(run_dir / "model_answer_evaluations.csv")
    if not existing_answer_rows:
        stream_writer.reset_stage_outputs("answer")
    new_answer_rows = build_answer_rows(
        query_rows,
        models,
        retrieval_evidence,
        caller=caller,
        orchestrator=orchestrator,
        stream_writer=stream_writer,
        completed_keys={result_key(row) for row in existing_answer_rows},
    )
    answer_rows = existing_answer_rows + new_answer_rows
    write_csv(run_dir / "model_answer_evaluations.csv", answer_rows, ANSWER_FIELDS)
    brand_rows = build_brand_performance_by_model(
        target_brand=str(config.get("campaign", {}).get("target_brand", "")),
        configured_brands=[str(item) for item in config.get("campaign", {}).get("competitors", [])],
        retrieval_evidence=retrieval_evidence,
        answer_rows=answer_rows,
    )
    write_csv(run_dir / "brand_performance_by_model.csv", brand_rows, BRAND_PERFORMANCE_FIELDS)
    dimension_rows = build_dimension_breakdown(retrieval_rows, str(config.get("campaign", {}).get("target_brand", "")))
    write_csv(run_dir / "dimension_breakdown.csv", dimension_rows, DIMENSION_FIELDS)
    report = build_competitive_gap_report(
        target_brand=str(config.get("campaign", {}).get("target_brand", "")),
        brand_rows=brand_rows,
        retrieval_rows=retrieval_rows,
        retrieval_evidence=retrieval_evidence,
        answer_rows=answer_rows,
        corpus_stats=load_corpus_stats(),
    )
    (run_dir / "competitive_gap_report.md").write_text(report, encoding="utf-8")
    attempts_path = run_dir / "api_orchestrator_attempts.jsonl"
    if attempts_path.exists():
        write_csv(run_dir / "api_call_summary.csv", build_api_call_summary(read_jsonl_rows(attempts_path)), API_CALL_SUMMARY_FIELDS)
    return {
        "queries": len(query_rows),
        "scenario_api_attempts": len(scenario_attempts),
        "rerank_api_attempts": len(rerank_attempts),
        "answer_api_attempts": len(answer_rows),
        "run_dir": str(run_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run API-first client acquisition GEO simulation.")
    parser.add_argument("--config", default="config/client_acquisition_simulator.yaml")
    args = parser.parse_args()
    result = run_simulator(load_config(Path(args.config)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
