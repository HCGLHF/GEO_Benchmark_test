from pathlib import Path

import pytest

from scripts.geo_eval.orchestrator import ModelCallOrchestrator, build_task_fingerprint
from scripts.geo_eval.run_state import RunState


def test_task_fingerprint_changes_when_temperature_or_repeat_changes():
    base = {
        "provider": "openrouter",
        "model": "model-a",
        "task_type": "rerank",
        "prompt": "rank candidates",
        "input_hash": "input-a",
        "config_hash": "config-a",
        "matrix_hash": "matrix-a",
        "corpus_hash": "corpus-a",
        "prompt_version": "rerank-v1",
    }

    first = build_task_fingerprint(**base, temperature=0.0, repeat_index=0)
    second = build_task_fingerprint(**base, temperature=0.2, repeat_index=0)
    third = build_task_fingerprint(**base, temperature=0.0, repeat_index=1)

    assert first != second
    assert first != third


def test_orchestrated_model_call_uses_cache_and_marks_complete(tmp_path: Path):
    calls = {"count": 0}

    def fake_call(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": f"answer {calls['count']}", "latency_ms": 10}

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=fake_call,
    )
    model_config = {"provider": "openrouter", "model": "model-a"}

    first = orchestrator.call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        query_id="q001",
        input_hash="input-a",
        prompt_version="answer-v1",
    )
    second = orchestrator.call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        query_id="q001",
        input_hash="input-a",
        prompt_version="answer-v1",
    )

    assert first["raw_answer"] == "answer 1"
    assert second["raw_answer"] == "answer 1"
    assert second["cache_hit"] is True
    assert calls["count"] == 1
    assert RunState(tmp_path / "state.sqlite").status("answer", "q001", "model-a", second["task_fingerprint"]) == "complete"
    events = (tmp_path / "api_call_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [line for line in events if '"status": "started"' in line]
    assert [line for line in events if '"status": "completed"' in line]
    assert [line for line in events if '"status": "cache_hit"' in line]


def test_orchestrated_model_call_does_not_cache_failures(tmp_path: Path):
    calls = {"count": 0}

    def failing_call(model_config, prompt, temperature):
        calls["count"] += 1
        raise RuntimeError("temporary provider failure")

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )
    model_config = {"provider": "openrouter", "model": "model-a"}

    with pytest.raises(RuntimeError):
        orchestrator.call(model_config, "prompt", 0.2, "answer", "q001", "input-a", "answer-v1")
    with pytest.raises(RuntimeError):
        orchestrator.call(model_config, "prompt", 0.2, "answer", "q001", "input-a", "answer-v1")

    assert calls["count"] == 2
    state = RunState(tmp_path / "state.sqlite")
    assert state.status("answer", "q001", "model-a", orchestrator.last_task_fingerprint) == "failed"
    events = (tmp_path / "api_call_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in events if '"status": "started"' in line) == 2
    assert sum(1 for line in events if '"status": "error"' in line) == 2
