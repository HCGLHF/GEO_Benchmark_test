from pathlib import Path

from scripts.geo_eval.llm_cache import LLMCache, cache_key_for_call
from scripts.geo_eval.models import cached_chat_call


def test_cache_key_is_stable_for_same_inputs():
    left = cache_key_for_call(
        provider="openrouter",
        model="openai/gpt-4.1-mini",
        task_type="rerank",
        prompt="Rank these candidates",
        input_hash="abc",
        config_hash="cfg",
    )
    right = cache_key_for_call(
        provider="openrouter",
        model="openai/gpt-4.1-mini",
        task_type="rerank",
        prompt="Rank these candidates",
        input_hash="abc",
        config_hash="cfg",
    )

    assert left == right
    assert left.startswith("llmcache_")


def test_cache_round_trip(tmp_path: Path):
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    key = cache_key_for_call("openrouter", "model-a", "answer", "prompt", "input", "cfg")

    assert cache.get(key) is None

    cache.put(
        key=key,
        provider="openrouter",
        model="model-a",
        task_type="answer",
        prompt_hash="prompt-hash",
        input_hash="input",
        config_hash="cfg",
        response={"raw_answer": "AlphaXXXX can help.", "latency_ms": 123},
    )

    cached = cache.get(key)
    assert cached["raw_answer"] == "AlphaXXXX can help."
    assert cached["latency_ms"] == 123


def test_cache_does_not_overwrite_existing_response(tmp_path: Path):
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    key = cache_key_for_call("openrouter", "model-a", "answer", "prompt", "input", "cfg")

    cache.put(key, "openrouter", "model-a", "answer", "p", "i", "c", {"raw_answer": "first"})
    cache.put(key, "openrouter", "model-a", "answer", "p", "i", "c", {"raw_answer": "second"})

    assert cache.get(key)["raw_answer"] == "first"


def test_cached_chat_call_uses_cache_on_second_call(tmp_path: Path):
    calls = {"count": 0}

    def fake_call(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": f"answer {calls['count']}", "latency_ms": 10}

    model_config = {"provider": "openrouter", "model": "model-a"}
    cache_path = tmp_path / "llm_cache.sqlite"

    first = cached_chat_call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        input_hash="query-1",
        config_hash="cfg",
        cache_path=cache_path,
        uncached_call=fake_call,
    )
    second = cached_chat_call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        input_hash="query-1",
        config_hash="cfg",
        cache_path=cache_path,
        uncached_call=fake_call,
    )

    assert first["raw_answer"] == "answer 1"
    assert second["raw_answer"] == "answer 1"
    assert second["cache_hit"] is True
    assert calls["count"] == 1
