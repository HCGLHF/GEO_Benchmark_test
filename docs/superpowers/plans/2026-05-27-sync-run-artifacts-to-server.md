# Run Artifact Server Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync all completed `quick` and `standard` full API run outputs, especially `competitive_gap_report.md`, to the shared server artifact store.

**Architecture:** Treat the existing AWS setup as the server: S3 stores run files and PostgreSQL `artifact_objects` records each uploaded artifact. Add one reusable sync command that discovers eligible run directories, attaches them to an explicit `corpus_version`, builds stable S3 keys, uploads files idempotently, and registers hashes in the existing artifact registry.

**Tech Stack:** Python 3.11, boto3, psycopg, existing `scripts.cloud` helpers, pytest.

---

## Assumptions

- "quik" means the existing `quick` run mode in `scripts/full_api_parallel_runner.py`.
- "server" means the current AWS S3 + RDS setup documented in `docs/cloud-database.md`.
- Only completed `quick` and `standard` runs should be synced by default; `test`, smoke, local-safe, and manual runs stay local unless the command is run with an explicit include flag.
- The first implementation should upload run artifacts only. It should not import per-query result rows into `benchmark_runs`, `retrieval_results`, or `generation_results` until the artifact sync path is proven stable.
- The current corpus version for these historical runs should be passed explicitly, for example `--corpus-version 2026-05-22-initial`.

## File Structure

- Create: `scripts/cloud/sync_run_artifacts.py`
  - Discovers eligible run roots.
  - Selects the canonical merged result directory.
  - Builds S3 object keys under `industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/...`.
  - Uploads selected files and registers artifact rows in PostgreSQL.
- Create: `tests/test_sync_run_artifacts.py`
  - Covers run discovery, quick/standard filtering, artifact selection, S3 key generation, dry-run behavior, and skip behavior for already-registered hashes.
- Modify: `scripts/full_api_parallel_runner.py`
  - Add an optional `--sync-artifacts` flag after merge/report completes.
  - Keep default behavior unchanged.
- Modify: `docs/cloud-database.md`
  - Document the historical backfill command and the optional automatic sync flag.

## Canonical Server Layout

Use these S3 keys for canonical merged outputs:

```text
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/manifest/run_manifest.json
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/manifest/merge_manifest.json
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/reports/competitive_gap_report.md
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/brand_performance_by_model.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/dimension_breakdown.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/retrieval_by_model.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/model_answer_evaluations.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/api_call_summary.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/query_loss_analysis.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/competitor_displacements.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/page_optimization_plan.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/owned_top5_pages.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/tables/owned_weak_pages.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/jsonl/retrieval_evidence_by_model.jsonl
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/logs/pipeline_state.jsonl
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/ui/progress.html
```

Use these S3 keys for per-model worker outputs when `--include-worker-artifacts` is passed or when no merged output exists:

```text
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/models/{model_safe_name}/reports/competitive_gap_report.md
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/models/{model_safe_name}/tables/retrieval_by_model.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/models/{model_safe_name}/tables/model_answer_evaluations.csv
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/models/{model_safe_name}/jsonl/retrieval_evidence_by_model.jsonl
```

Use these `artifact_type` values:

```text
run_manifest
merge_manifest
competitive_gap_report
brand_performance_by_model
dimension_breakdown
retrieval_by_model
model_answer_evaluations
api_call_summary
query_loss_analysis
competitor_displacements
page_optimization_plan
owned_top5_pages
owned_weak_pages
retrieval_evidence_by_model
pipeline_state
progress_html
```

## Historical Backfill Operation

After implementation, run these from `D:\GEO-ALPHA\Resourcepool_Gen`:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel --run-mode quick --run-mode standard --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_alpha_refresh_quick_final --run-mode quick --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --dry-run
```

Review the printed run count, artifact count, total bytes, and skipped runs. Then execute:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel --run-mode quick --run-mode standard --execute
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_alpha_refresh_quick_final --run-mode quick --execute
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --execute
```

## Future Run Operation

Once the runner flag is implemented, run quick or standard jobs like this:

```powershell
python scripts\full_api_parallel_runner.py --run-mode quick --sync-artifacts --corpus-version 2026-05-22-initial
python scripts\full_api_parallel_runner.py --run-mode standard --sync-artifacts --corpus-version 2026-05-22-initial
```

The runner should call the sync command only after merge/report finishes successfully.

---

### Task 1: Add Discovery And Artifact Planning Tests

**Files:**
- Create: `tests/test_sync_run_artifacts.py`
- Create: `scripts/cloud/sync_run_artifacts.py`

- [ ] **Step 1: Write failing tests for run discovery**

Add tests that create temporary run roots with:

```text
runs/full_api_parallel_ui/20260526_002837/run_manifest.json
runs/full_api_parallel_ui/20260526_002837/merged/competitive_gap_report.md
runs/full_api_parallel_ui/20260526_002837/merged/brand_performance_by_model.csv
runs/full_api_parallel_ui/20260526_002837/merged/merge_manifest.json
```

Expected behavior:

```python
from pathlib import Path

from scripts.cloud.sync_run_artifacts import discover_run_roots


def test_discover_run_roots_keeps_quick_and_standard(tmp_path: Path):
    quick = tmp_path / "full_api_parallel_ui" / "20260526_002837"
    quick.mkdir(parents=True)
    (quick / "run_manifest.json").write_text(
        '{"status":"completed","metadata":{"run_mode":"quick","queries_per_model":50}}',
        encoding="utf-8",
    )
    merged = quick / "merged"
    merged.mkdir()
    (merged / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")

    test = tmp_path / "full_api_parallel_ui" / "20260526_010000"
    test.mkdir(parents=True)
    (test / "run_manifest.json").write_text(
        '{"status":"completed","metadata":{"run_mode":"test","queries_per_model":2}}',
        encoding="utf-8",
    )
    (test / "merged").mkdir()
    (test / "merged" / "competitive_gap_report.md").write_text("# Test\n", encoding="utf-8")

    roots = discover_run_roots([tmp_path / "full_api_parallel_ui"], {"quick", "standard"})

    assert roots == [quick]
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py::test_discover_run_roots_keeps_quick_and_standard -v
```

Expected: FAIL because `scripts.cloud.sync_run_artifacts` does not exist.

### Task 2: Implement Run Discovery

**Files:**
- Modify: `scripts/cloud/sync_run_artifacts.py`
- Test: `tests/test_sync_run_artifacts.py`

- [ ] **Step 1: Implement minimal discovery**

Implementation rules:

- Candidate run roots are directories under each `--run-root`.
- A run is eligible when it has a `competitive_gap_report.md` in `merged/`, `merged_3_models/`, or `merged_with_page_drilldown/`.
- Prefer `merged/` when multiple merged directories exist.
- Read `run_manifest.json` for `metadata.run_mode`.
- If `run_manifest.json` is missing, infer `quick` only when the parent path contains `quick`; do not infer `standard` from old directories without a manifest.
- Ignore runs whose manifest status is `failed`.

- [ ] **Step 2: Run discovery tests**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py -v
```

Expected: discovery tests pass.

### Task 3: Add Artifact Planning And S3 Key Tests

**Files:**
- Modify: `tests/test_sync_run_artifacts.py`
- Modify: `scripts/cloud/sync_run_artifacts.py`

- [ ] **Step 1: Write failing tests for artifact plans**

Expected behavior:

```python
from scripts.cloud.sync_run_artifacts import build_run_artifact_plan


def test_build_run_artifact_plan_uses_stable_server_keys(tmp_path: Path):
    run_root = tmp_path / "full_api_parallel_ui" / "20260526_002837"
    merged = run_root / "merged"
    merged.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(
        '{"metadata":{"run_mode":"quick","queries_per_model":50}}',
        encoding="utf-8",
    )
    (merged / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
    (merged / "brand_performance_by_model.csv").write_text("model,brand\n", encoding="utf-8")

    plan = build_run_artifact_plan(
        industry_id="geo-agency",
        corpus_version="2026-05-22-initial",
        run_root=run_root,
        run_mode="quick",
        merged_dir=merged,
    )

    keys = {item["artifact_type"]: item["object_key"] for item in plan["artifacts"]}
    assert keys["competitive_gap_report"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/reports/competitive_gap_report.md"
    )
    assert keys["brand_performance_by_model"] == (
        "industries/geo-agency/runs/2026-05-22-initial/quick/20260526_002837/tables/brand_performance_by_model.csv"
    )
```

- [ ] **Step 2: Run the key test and verify it fails**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py::test_build_run_artifact_plan_uses_stable_server_keys -v
```

Expected: FAIL because artifact planning is not implemented.

### Task 4: Implement Artifact Planning

**Files:**
- Modify: `scripts/cloud/sync_run_artifacts.py`
- Test: `tests/test_sync_run_artifacts.py`

- [ ] **Step 1: Implement file selection**

Include files only if they exist. Required file:

```text
competitive_gap_report.md
```

Optional files:

```text
run_manifest.json
merge_manifest.json
brand_performance_by_model.csv
dimension_breakdown.csv
retrieval_by_model.csv
model_answer_evaluations.csv
api_call_summary.csv
query_loss_analysis.csv
competitor_displacements.csv
page_optimization_plan.csv
owned_top5_pages.csv
owned_weak_pages.csv
retrieval_evidence_by_model.jsonl
pipeline_state.jsonl
progress.html
```

- [ ] **Step 2: Reuse existing hash logic**

Use `scripts.cloud.s3_artifacts.sha256_file` so the sync command and corpus artifact commands use the same hash behavior.

- [ ] **Step 3: Run tests**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py -v
```

Expected: all sync artifact tests pass.

### Task 5: Add Dry-Run And Execute Command

**Files:**
- Modify: `scripts/cloud/sync_run_artifacts.py`
- Test: `tests/test_sync_run_artifacts.py`

- [ ] **Step 1: Add CLI arguments**

Required arguments:

```text
--industry
--corpus-version
--run-root
--run-mode
```

Execution switches:

```text
--dry-run
--execute
--skip-s3
--skip-db
--include-worker-artifacts
```

Behavior:

- `--dry-run` prints JSON and writes nothing.
- `--execute` uploads to S3 unless `--skip-s3` is set.
- `--execute` registers artifact rows unless `--skip-db` is set.
- If neither `--dry-run` nor `--execute` is passed, default to dry-run.

- [ ] **Step 2: Add injectable upload/register dependencies for tests**

The core function should accept optional `upload_fn` and `register_fn` callables so tests do not hit AWS or RDS.

- [ ] **Step 3: Run tests**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py -v
```

Expected: dry-run tests pass without network access.

### Task 6: Wire Optional Sync Into Future Runs

**Files:**
- Modify: `scripts/full_api_parallel_runner.py`
- Test: `tests/test_full_api_parallel_runner.py`

- [ ] **Step 1: Add `--sync-artifacts` and `--corpus-version` to runner options**

Add a boolean `sync_artifacts` field and a string `corpus_version` field to `RunnerOptions`. Parse `--sync-artifacts` as a flag and `--corpus-version` as an optional value defaulting to `2026-05-22-initial`.

- [ ] **Step 2: Call sync after successful merge/report**

After `append_event(run_root, stage="report", status="completed", ...)`, call the sync function with:

```text
industry_id=geo-agency
corpus_version=options.corpus_version
run_roots=[run_root.parent]
run_modes={options.run_mode}
```

The first pass can hard-code `geo-agency` because the current cloud default is `geo-agency`; add `--industry` later if another industry starts running API benchmarks.

- [ ] **Step 3: Add runner test**

Test that `--sync-artifacts` is parsed and does not affect default dry-run output unless explicitly passed.

- [ ] **Step 4: Run runner tests**

Run:

```powershell
pytest tests\test_full_api_parallel_runner.py tests\test_sync_run_artifacts.py -v
```

Expected: all tests pass.

### Task 7: Document And Execute Historical Backfill

**Files:**
- Modify: `docs/cloud-database.md`

- [ ] **Step 1: Add documentation section**

Add a "Run Artifact Sync" section with:

- Purpose: S3 holds run outputs; PostgreSQL `artifact_objects` records hashes and object keys.
- Dry-run command.
- Execute command.
- Exact S3 key shape.
- Warning that `.env` must contain AWS and database credentials.

- [ ] **Step 2: Run complete verification**

Run:

```powershell
pytest tests\test_sync_run_artifacts.py tests\test_full_api_parallel_runner.py tests\test_cloud_qdrant_snapshot.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run historical dry-runs**

Run:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel --run-mode quick --run-mode standard --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_alpha_refresh_quick_final --run-mode quick --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --dry-run
```

Expected:

- Runs with merged `competitive_gap_report.md` are listed.
- `test` runs are skipped.
- Failed runs are skipped.
- Total artifacts and bytes are printed.

- [ ] **Step 4: Execute historical sync**

Run:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel --run-mode quick --run-mode standard --execute
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_alpha_refresh_quick_final --run-mode quick --execute
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --execute
```

Expected:

- S3 upload succeeds for every planned artifact.
- PostgreSQL `artifact_objects` contains one row per uploaded artifact.
- Re-running the same command is idempotent because rows are upserted by `(industry_id, corpus_version, artifact_type, object_key)`.

## Self-Review

- Spec coverage: The plan covers all quick/standard full API run outputs and prioritizes `competitive_gap_report.md`.
- Placeholder scan: No `TBD` or open-ended implementation placeholders are used.
- Type consistency: Function names are stable across tasks: `discover_run_roots` and `build_run_artifact_plan`.
