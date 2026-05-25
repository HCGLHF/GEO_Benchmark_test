import json
from pathlib import Path

import pytest

import scripts.geo_eval.orchestrator as orchestrator_module
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
    attempts = [
        json.loads(line)
        for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(attempts) == 2
    assert attempts[0]["status"] == "error"
    assert attempts[0]["cache_hit"] is False


def test_orchestrated_model_call_logs_ops_event_on_api_failure(tmp_path: Path):
    def failing_call(model_config, prompt, temperature):
        raise RuntimeError("OpenRouter 429 Too Many Requests")

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["level"] == "warning"
    assert events[0]["event_type"] == "api_failure"
    assert events[0]["stage"] == "answer"
    assert events[0]["model"] == "model-a"
    assert events[0]["details"]["query_id"] == "q001"
    assert "429" in events[0]["details"]["error"]


def test_orchestrated_model_call_logs_ops_event_to_parent_run_root(tmp_path: Path):
    parent_run_root = tmp_path / "parallel"
    model_run_root = parent_run_root / "model-a"

    def failing_call(model_config, prompt, temperature):
        raise RuntimeError("OpenRouter 429 Too Many Requests")

    orchestrator = ModelCallOrchestrator(
        cache_path=model_run_root / "cache.sqlite",
        run_state_path=model_run_root / "state.sqlite",
        attempts_path=model_run_root / "api_orchestrator_attempts.jsonl",
        ops_run_root=parent_run_root,
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    parent_events = [
        json.loads(line)
        for line in (parent_run_root / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert parent_events[0]["event_type"] == "api_failure"
    assert parent_events[0]["model"] == "model-a"
    assert not (model_run_root / "ops_events.jsonl").exists()


def test_orchestrated_model_call_bounds_ops_error_but_preserves_attempt_error(tmp_path: Path):
    prompt_fragment = "PROMPT_FRAGMENT_DO_NOT_COPY"
    full_error = "OpenRouter 429 Too Many Requests " + ("x" * 520) + prompt_fragment

    def failing_call(model_config, prompt, temperature):
        raise RuntimeError(full_error)

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    attempts = [
        json.loads(line)
        for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert len(events[0]["message"]) <= 500
    assert len(events[0]["details"]["error"]) <= 500
    assert events[0]["message"].endswith("...")
    assert events[0]["details"]["error"].endswith("...")
    assert prompt_fragment not in events[0]["message"]
    assert prompt_fragment not in events[0]["details"]["error"]
    assert attempts[0]["error"] == full_error


def test_orchestrated_model_call_redacts_sensitive_ops_error_but_preserves_attempt_error(tmp_path: Path):
    raw_error = (
        'Authorization: Bearer sk-secret-value prompt: "PROMPT_FRAGMENT_DO_NOT_COPY" '
        'messages: [{"content":"MESSAGE_FRAGMENT_DO_NOT_COPY"}] '
        "OpenRouter 429 Too Many Requests"
    )

    def failing_call(model_config, prompt, temperature):
        raise RuntimeError(raw_error)

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    attempts = [
        json.loads(line)
        for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    for ops_text in [events[0]["message"], events[0]["details"]["error"]]:
        assert "sk-secret-value" not in ops_text
        assert "PROMPT_FRAGMENT_DO_NOT_COPY" not in ops_text
        assert "MESSAGE_FRAGMENT_DO_NOT_COPY" not in ops_text
        assert "429" in ops_text or "Too Many Requests" in ops_text
    assert attempts[0]["error"] == raw_error


def test_orchestrated_model_call_redacts_json_shaped_ops_error_but_preserves_attempt_error(tmp_path: Path):
    raw_error = (
        '{"prompt":"PROMPT_FRAGMENT_DO_NOT_COPY",'
        '"messages":[{"content":"MESSAGE_FRAGMENT_DO_NOT_COPY"}],'
        '"api_key":"sk-secret-value"} OpenRouter 429'
    )

    def failing_call(model_config, prompt, temperature):
        raise RuntimeError(raw_error)

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    attempts = [
        json.loads(line)
        for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    for ops_text in [events[0]["message"], events[0]["details"]["error"]]:
        assert "sk-secret-value" not in ops_text
        assert "PROMPT_FRAGMENT_DO_NOT_COPY" not in ops_text
        assert "MESSAGE_FRAGMENT_DO_NOT_COPY" not in ops_text
        assert "429" in ops_text
    assert attempts[0]["error"] == raw_error


def test_orchestrated_model_call_redacts_json_authorization_ops_error_but_preserves_attempt_error(tmp_path: Path):
    raw_error = '{"Authorization":"Bearer sk-secret-value"} OpenRouter 429'

    def failing_call(model_config, prompt, temperature):
        raise RuntimeError(raw_error)

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    attempts = [
        json.loads(line)
        for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    for ops_text in [events[0]["message"], events[0]["details"]["error"]]:
        assert "sk-secret-value" not in ops_text
        assert "429" in ops_text
    assert attempts[0]["error"] == raw_error


def test_orchestrated_model_call_preserves_model_exception_when_ops_logging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def failing_call(model_config, prompt, temperature):
        raise RuntimeError("original provider failure")

    def failing_ops_logger(*args, **kwargs):
        raise RuntimeError("ops logging failed")

    monkeypatch.setattr(orchestrator_module, "safe_write_event", failing_ops_logger)
    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError, match="original provider failure"):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )
