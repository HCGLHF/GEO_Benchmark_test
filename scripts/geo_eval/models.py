from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from typing import Callable

import httpx

from scripts._common import load_dotenv, stable_id, utc_now_iso
from scripts.geo_eval.llm_cache import LLMCache, cache_key_for_call
from scripts.geo_eval.llm_cache import stable_hash
from scripts.geo_eval.io import output_dir, read_csv, read_jsonl, write_json, write_jsonl
from scripts.geo_eval.retrieval import retrieval_summary


def direct_config(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("model_run", {}).get("direct", {})


def should_run_direct(config: dict[str, Any], summary: dict[str, Any]) -> tuple[bool, str]:
    cfg = direct_config(config)
    if not cfg.get("enabled", True):
        return False, "disabled"
    if cfg.get("recall_gate", "block") != "block":
        return True, "enabled"
    min_recall = float(cfg.get("min_recall_at_5", 0.5))
    if float(summary.get("recall_at_5", 0.0)) < min_recall:
        return False, "blocked_by_recall_gate"
    return True, "enabled"


def model_response_key(provider: str, model: str, mode: str, query_id: str, repeat_index: int, prompt: str) -> str:
    return stable_id("mresp", f"{provider}:{model}:{mode}:{query_id}:{repeat_index}:{prompt}")


def build_direct_prompt(query: str) -> str:
    return (
        "You are helping a buyer make a practical decision. Answer the user's question directly. "
        "If you recommend vendors, explain why and mention trade-offs. Do not assume the user wants "
        "a specific brand unless the question says so.\n\n"
        f"User question: {query}"
    )


def provider_endpoint(model_config: dict[str, Any]) -> str:
    if model_config.get("base_url"):
        return str(model_config["base_url"]).rstrip("/") + "/chat/completions"
    provider = str(model_config.get("provider", "")).lower()
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1/chat/completions"
    if provider == "perplexity":
        return "https://api.perplexity.ai/chat/completions"
    return "https://api.openai.com/v1/chat/completions"


def build_chat_payload(model_config: dict[str, Any], prompt: str, temperature: float) -> dict[str, Any]:
    return {
        "model": model_config["model"],
        "temperature": temperature,
        "context_policy": "clean",
        "messages": [
            {"role": "system", "content": "You are a neutral research assistant evaluating vendors and sources."},
            {"role": "user", "content": prompt},
        ],
    }


def api_headers(model_config: dict[str, Any], api_key: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if str(model_config.get("provider", "")).lower() == "openrouter":
        headers["HTTP-Referer"] = str(model_config.get("http_referer", "https://alphaxxxx.com"))
        headers["X-Title"] = str(model_config.get("app_title", "AlphaXXXX GEO Evaluator"))
    return headers


def call_chat_model(model_config: dict[str, Any], prompt: str, temperature: float) -> dict[str, Any]:
    load_dotenv()
    api_key_env = str(model_config.get("api_key_env", "OPENAI_API_KEY"))
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key env: {api_key_env}")

    payload = build_chat_payload(model_config, prompt, temperature)
    api_payload = {key: value for key, value in payload.items() if key != "context_policy"}
    started = time.perf_counter()
    response = httpx.post(
        provider_endpoint(model_config),
        headers=api_headers(model_config, api_key),
        json=api_payload,
        timeout=float(model_config.get("timeout_seconds", 90)),
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    payload = response.json()
    text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    citations = payload.get("citations") or payload.get("search_results") or []
    return {"raw_answer": text, "citations": citations, "latency_ms": latency_ms, "raw": payload}


def cached_chat_call(
    model_config: dict[str, Any],
    prompt: str,
    temperature: float,
    task_type: str,
    input_hash: str,
    config_hash: str,
    cache_path: Path,
    uncached_call: Callable[[dict[str, Any], str, float], dict[str, Any]] = call_chat_model,
) -> dict[str, Any]:
    provider = str(model_config.get("provider", "openai"))
    model = str(model_config.get("model", ""))
    key = cache_key_for_call(provider, model, task_type, prompt, input_hash, config_hash)
    cache = LLMCache(cache_path)
    cached = cache.get(key)
    if cached is not None:
        return cached | {"cache_hit": True}
    result = uncached_call(model_config, prompt, temperature)
    cache.put(
        key=key,
        provider=provider,
        model=model,
        task_type=task_type,
        prompt_hash=stable_hash(prompt),
        input_hash=input_hash,
        config_hash=config_hash,
        response=result,
    )
    return result | {"cache_hit": False}


def run_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    run_dir = output_dir(config)
    retrieval_rows = read_csv(run_dir / "retrieval_evaluations.csv")
    summary = retrieval_summary(retrieval_rows)
    allowed, reason = should_run_direct(config, summary)
    status = {
        "direct_allowed": allowed,
        "reason": reason,
        "recall_at_5": summary["recall_at_5"],
        "min_recall_at_5": float(direct_config(config).get("min_recall_at_5", 0.5)),
        "checked_at": utc_now_iso(),
    }
    write_json(run_dir / "model_run_status.json", status)

    responses_path = run_dir / "model_responses.jsonl"
    existing = read_jsonl(responses_path)
    if not allowed:
        return existing

    models = config.get("models") or []
    if not models:
        return existing

    queries = read_csv(run_dir / "queries.csv")[: int(direct_config(config).get("max_queries", 50))]
    repeats = int(direct_config(config).get("repeats_per_query", 1))
    temperature = float(config.get("model_run", {}).get("temperature", 0.2))
    existing_keys = {row.get("response_key") for row in existing}
    responses = list(existing)

    for model_config in models:
        provider = str(model_config.get("provider", "openai"))
        model = str(model_config.get("model", ""))
        for query in queries:
            prompt = build_direct_prompt(query["query"])
            for repeat_index in range(repeats):
                response_key = model_response_key(provider, model, "direct", query["query_id"], repeat_index, prompt)
                if response_key in existing_keys:
                    continue
                try:
                    result = call_chat_model(model_config, prompt, temperature)
                    response_row = {
                        "response_id": response_key,
                        "response_key": response_key,
                        "query_id": query["query_id"],
                        "query": query["query"],
                        "provider": provider,
                        "model": model,
                        "mode": "direct",
                        "repeat_index": repeat_index,
                        "prompt": prompt,
                        "context_policy": "clean",
                        "message_count": 2,
                        "raw_answer": result["raw_answer"],
                        "citations": result["citations"],
                        "latency_ms": result["latency_ms"],
                        "error": None,
                        "created_at": utc_now_iso(),
                    }
                except Exception as exc:
                    response_row = {
                        "response_id": response_key,
                        "response_key": response_key,
                        "query_id": query["query_id"],
                        "query": query["query"],
                        "provider": provider,
                        "model": model,
                        "mode": "direct",
                        "repeat_index": repeat_index,
                        "prompt": prompt,
                        "context_policy": "clean",
                        "message_count": 2,
                        "raw_answer": "",
                        "citations": [],
                        "latency_ms": None,
                        "error": str(exc),
                        "created_at": utc_now_iso(),
                    }
                existing_keys.add(response_key)
                responses.append(response_row)
                write_jsonl(responses_path, responses)
    return responses
