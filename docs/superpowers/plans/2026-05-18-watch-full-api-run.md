# Watch Full API Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only monitor for long full API client acquisition simulator runs.

**Architecture:** Create one focused CLI script that reads a run directory and summarizes progress from existing output files. Keep monitoring separate from API orchestration and run-state mutation so it can safely inspect active runs.

**Tech Stack:** Python standard library, pytest.

---

### Task 1: Monitor Summary Core

**Files:**
- Create: `scripts/watch_full_api_run.py`
- Create: `tests/test_watch_full_api_run.py`

- [x] **Step 1: Write failing tests**

```python
from scripts.watch_full_api_run import summarize_run

def test_summarize_run_counts_attempts_by_model_and_task(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # Write run_config.resolved.json, api_queries.csv, model_answer_evaluations.csv,
    # and api_orchestrator_attempts.jsonl.
    summary = summarize_run(run_dir)
    assert summary["totals"]["queries"] == 2
    assert summary["tasks"]["answer"]["api_calls"] == 1
    assert summary["models"]["model-a"]["failures"] == 1
```

- [x] **Step 2: Verify test fails**

Run: `pytest tests/test_watch_full_api_run.py -q`

Expected: import error because `scripts.watch_full_api_run` does not exist.

- [x] **Step 3: Implement minimal summary code**

Implement:
- CSV row counting
- JSONL row reading with malformed-line tolerance
- task/model aggregation for `api_orchestrator_attempts.jsonl`
- expected call estimation from `run_config.resolved.json`
- status classification as `complete`, `active`, `idle`, or `empty`

- [x] **Step 4: Verify tests pass**

Run: `pytest tests/test_watch_full_api_run.py -q`

Expected: all tests pass.

### Task 2: CLI Output

**Files:**
- Modify: `scripts/watch_full_api_run.py`
- Modify: `tests/test_watch_full_api_run.py`

- [x] **Step 1: Write failing CLI tests**

```python
from scripts.watch_full_api_run import format_text_report

def test_format_text_report_includes_progress_and_failures(sample_summary):
    report = format_text_report(sample_summary)
    assert "Run:" in report
    assert "Progress:" in report
    assert "Failures:" in report
```

- [x] **Step 2: Implement CLI**

Add:
- `--run-dir`
- `--latest`
- `--runs-root`
- `--json`
- plain text report formatting

- [x] **Step 3: Verify CLI behavior**

Run:
`python scripts/watch_full_api_run.py --run-dir runs/client_acquisition_simulator_full_api_20260517_200716`

Expected: prints progress, model breakdown, task breakdown, and failure summary without calling APIs.

### Task 3: Project Memory And Full Verification

**Files:**
- Modify: `docs/next.md`

- [x] **Step 1: Update project memory**

Record that the read-only full API monitor was added and note remaining risks around incremental output streaming.

- [x] **Step 2: Run focused and full tests**

Run:
- `pytest tests/test_watch_full_api_run.py -q`
- `pytest -q`

Expected: all tests pass.
