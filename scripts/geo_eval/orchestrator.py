from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from scripts._common import utc_now_iso
from scripts.geo_eval.llm_cache import LLMCache, cache_key_for_call, stable_hash
from scripts.geo_eval.models import call_chat_model
from scripts.geo_eval.run_state import RunState


ChatCaller = Callable[[dict[str, Any], str, float], dict[str, Any]]


def canonical_hash(value: Any) -> str:
    return stable_hash(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str))


def build_task_fingerprint(
    provider: str,
    model: str,
    task_type: str,
    prompt: str,
    input_hash: str,
    config_hash: str,
    matrix_hash: str,
    corpus_hash: str,
    prompt_version: str,
    temperature: float,
    repeat_index: int = 0,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "prompt_hash": stable_hash(prompt),
        "input_hash": input_hash,
        "config_hash": config_hash,
        "matrix_hash": matrix_hash,
        "corpus_hash": corpus_hash,
        "prompt_version": prompt_version,
        "temperature": temperature,
        "repeat_index": repeat_index,
    }
    return "task_" + canonical_hash(payload)[:24]


class ModelCallOrchestrator:
    def __init__(
        self,
        cache_path: Path,
        run_state_path: Path,
        attempts_path: Path,
        config_hash: str,
        matrix_hash: str,
        corpus_hash: str,
        uncached_call: ChatCaller = call_chat_model,
    ):
        self.cache = LLMCache(Path(cache_path))
        self.run_state = RunState(Path(run_state_path))
        self.attempts_path = Path(attempts_path)
        self.attempts_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_hash = config_hash
        self.matrix_hash = matrix_hash
        self.corpus_hash = corpus_hash
        self.uncached_call = uncached_call
        self.last_task_fingerprint = ""

    def call(
        self,
        model_config: dict[str, Any],
        prompt: str,
        temperature: float,
        task_type: str,
        query_id: str,
        input_hash: str,
        prompt_version: str,
        repeat_index: int = 0,
    ) -> dict[str, Any]:
        provider = str(model_config.get("provider", "openai"))
        model = str(model_config.get("model", ""))
        task_fingerprint = build_task_fingerprint(
            provider=provider,
            model=model,
            task_type=task_type,
            prompt=prompt,
            input_hash=input_hash,
            config_hash=self.config_hash,
            matrix_hash=self.matrix_hash,
            corpus_hash=self.corpus_hash,
            prompt_version=prompt_version,
            temperature=temperature,
            repeat_index=repeat_index,
        )
        self.last_task_fingerprint = task_fingerprint
        cache_key = cache_key_for_call(provider, model, task_type, prompt, task_fingerprint, self.config_hash)
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.run_state.mark_complete(task_type, query_id, model, task_fingerprint)
            response = cached | {"cache_hit": True, "task_fingerprint": task_fingerprint}
            self._log_attempt(task_type, query_id, provider, model, task_fingerprint, "cache_hit", None, True)
            return response

        try:
            result = self.uncached_call(model_config, prompt, temperature)
        except Exception as exc:
            self.run_state.mark_failed(task_type, query_id, model, str(exc), task_fingerprint)
            self._log_attempt(task_type, query_id, provider, model, task_fingerprint, "error", str(exc), False)
            raise

        self.cache.put(
            key=cache_key,
            provider=provider,
            model=model,
            task_type=task_type,
            prompt_hash=stable_hash(prompt),
            input_hash=task_fingerprint,
            config_hash=self.config_hash,
            response=result,
        )
        self.run_state.mark_complete(task_type, query_id, model, task_fingerprint)
        self._log_attempt(task_type, query_id, provider, model, task_fingerprint, "api_call", None, False)
        return result | {"cache_hit": False, "task_fingerprint": task_fingerprint}

    def _log_attempt(
        self,
        task_type: str,
        query_id: str,
        provider: str,
        model: str,
        task_fingerprint: str,
        status: str,
        error: str | None,
        cache_hit: bool,
    ) -> None:
        row = {
            "task_type": task_type,
            "query_id": query_id,
            "provider": provider,
            "model": model,
            "task_fingerprint": task_fingerprint,
            "status": status,
            "error": error,
            "cache_hit": cache_hit,
            "created_at": utc_now_iso(),
        }
        with self.attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
