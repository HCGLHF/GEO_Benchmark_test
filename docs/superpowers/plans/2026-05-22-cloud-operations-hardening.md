# Cloud Operations Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the first successful AWS import into a repeatable, verifiable cloud operations path for the GEO resource library.

**Architecture:** Keep PostgreSQL as the queryable corpus and benchmark ledger, S3 as the artifact store, and Qdrant as a rebuildable retrieval index. Add small CLI tools under `scripts/cloud/` that reuse the existing `CloudConfig`, S3 artifact helpers, and PostgreSQL connection boundary instead of adding a broad service layer.

**Tech Stack:** Python, pytest, boto3, psycopg, PowerShell launcher scripts, AWS S3, AWS RDS PostgreSQL.

---

## File Structure

- Create `scripts/cloud/verify_cloud_import.py`: read-only verifier for RDS counts and S3 artifact presence.
- Create `tests/test_cloud_verify_import.py`: unit tests for verification summary logic without live AWS calls.
- Create `scripts/cloud/qdrant_snapshot.py`: zip local Qdrant storage, compute artifact metadata, optionally upload it to S3 and register it in PostgreSQL.
- Create `tests/test_cloud_qdrant_snapshot.py`: unit tests for zip creation and artifact key planning.
- Modify `scripts/cloud/postgres.py`: extract artifact registration so Qdrant snapshots can reuse the `artifact_objects` table without re-importing the whole corpus.
- Modify `scripts/seed_api_queries.py`: add stratified seeded query selection.
- Modify `tests/test_seed_api_queries.py`: prove quick runs can sample across persona and journey stage instead of taking the first rows only.
- Modify `scripts/run_full_api_parallel_with_watch.ps1`: pass stratified seed selection when `-RunMode quick` uses `-SeedQueriesRunDir`.
- Modify `tests/test_full_api_parallel_with_watch.py`: assert dry-run output shows the stratified seeding mode.
- Create `docs/cloud-operations.md`: human runbook for verify/import/snapshot/credential rotation.
- Modify `docs/architecture.md`, `docs/risks.md`, and `docs/next.md`: record the new cloud operations boundary and completed work.

---

### Task 1: Cloud Import Verifier

**Files:**
- Create: `scripts/cloud/verify_cloud_import.py`
- Create: `tests/test_cloud_verify_import.py`

- [x] **Step 1: Write failing tests for summary validation**

Add `tests/test_cloud_verify_import.py`:

```python
from scripts.cloud.verify_cloud_import import build_verification_result


def test_build_verification_result_passes_when_counts_and_artifacts_match():
    result = build_verification_result(
        corpus_version="2026-05-22-initial",
        expected_counts={"inventory_rows": 1683, "documents": 1683, "chunks": 6225, "artifacts": 3},
        db_counts={"inventory_rows": 1683, "documents": 1683, "chunks": 6225, "artifacts": 3},
        artifact_checks=[
            {"object_key": "raw/2026-05-22-initial/url_inventory.csv", "expected_size": 328092, "actual_size": 328092}
        ],
    )

    assert result["ok"] is True
    assert result["failures"] == []


def test_build_verification_result_reports_count_and_artifact_mismatches():
    result = build_verification_result(
        corpus_version="2026-05-22-initial",
        expected_counts={"inventory_rows": 1683, "documents": 1683, "chunks": 6225, "artifacts": 3},
        db_counts={"inventory_rows": 1683, "documents": 1682, "chunks": 6225, "artifacts": 3},
        artifact_checks=[
            {"object_key": "processed/2026-05-22-initial/documents.jsonl", "expected_size": 10, "actual_size": 9}
        ],
    )

    assert result["ok"] is False
    assert "documents expected 1683 but found 1682" in result["failures"]
    assert "processed/2026-05-22-initial/documents.jsonl expected 10 bytes but found 9" in result["failures"]
```

- [x] **Step 2: Run the focused failing test**

Run:

```powershell
pytest tests\test_cloud_verify_import.py -q
```

Expected: FAIL because `scripts.cloud.verify_cloud_import` does not exist.

- [x] **Step 3: Implement the verifier**

Create `scripts/cloud/verify_cloud_import.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.config import CloudConfig
from scripts.cloud.postgres import fetch_corpus_counts, fetch_artifact_rows


def build_verification_result(
    *,
    corpus_version: str,
    expected_counts: dict[str, int],
    db_counts: dict[str, int],
    artifact_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    failures: list[str] = []
    for key, expected in expected_counts.items():
        actual = db_counts.get(key)
        if actual != expected:
            failures.append(f"{key} expected {expected} but found {actual}")
    for check in artifact_checks:
        expected_size = check["expected_size"]
        actual_size = check.get("actual_size")
        if actual_size != expected_size:
            failures.append(
                f"{check['object_key']} expected {expected_size} bytes but found {actual_size}"
            )
    return {
        "ok": not failures,
        "corpus_version": corpus_version,
        "expected_counts": expected_counts,
        "db_counts": db_counts,
        "artifact_checks": artifact_checks,
        "failures": failures,
    }


def head_artifacts(*, bucket: str, region: str, artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Install boto3 to verify S3 artifacts.") from exc
    s3 = boto3.client("s3", region_name=region)
    checks: list[dict[str, Any]] = []
    for row in artifact_rows:
        try:
            response = s3.head_object(Bucket=bucket, Key=row["object_key"])
            actual_size = response["ContentLength"]
        except Exception:
            actual_size = None
        checks.append(
            {
                "artifact_type": row["artifact_type"],
                "object_key": row["object_key"],
                "expected_size": row["size_bytes"],
                "actual_size": actual_size,
            }
        )
    return checks


def verify_cloud_import(corpus_version: str) -> dict[str, Any]:
    config = CloudConfig.from_env()
    db_counts = fetch_corpus_counts(config.database_url, corpus_version)
    artifact_rows = fetch_artifact_rows(config.database_url, corpus_version)
    expected_counts = {
        "inventory_rows": db_counts["corpus_inventory_count"],
        "documents": db_counts["corpus_document_count"],
        "chunks": db_counts["corpus_chunk_count"],
        "artifacts": len(artifact_rows),
    }
    artifact_checks = head_artifacts(
        bucket=config.s3_bucket,
        region=config.aws_region,
        artifact_rows=artifact_rows,
    )
    return build_verification_result(
        corpus_version=corpus_version,
        expected_counts=expected_counts,
        db_counts=db_counts,
        artifact_checks=artifact_checks,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify an imported cloud corpus version.")
    parser.add_argument("--corpus-version", required=True)
    args = parser.parse_args()
    result = verify_cloud_import(args.corpus_version)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Add PostgreSQL read helpers**

Modify `scripts/cloud/postgres.py` by adding these functions after `execute_schema`:

```python
def fetch_corpus_counts(database_url: str, corpus_version: str) -> dict[str, int]:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT inventory_count, document_count, chunk_count
                FROM corpus_versions
                WHERE corpus_version = %s
                """,
                (corpus_version,),
            )
            version_row = cursor.fetchone()
            if version_row is None:
                raise ValueError(f"Corpus version not found: {corpus_version}")
            cursor.execute("SELECT count(*) FROM url_inventory WHERE corpus_version = %s", (corpus_version,))
            inventory_rows = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM documents WHERE corpus_version = %s", (corpus_version,))
            documents = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM chunks WHERE corpus_version = %s", (corpus_version,))
            chunks = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM artifact_objects WHERE corpus_version = %s", (corpus_version,))
            artifacts = cursor.fetchone()[0]
    return {
        "corpus_inventory_count": version_row[0],
        "corpus_document_count": version_row[1],
        "corpus_chunk_count": version_row[2],
        "inventory_rows": inventory_rows,
        "documents": documents,
        "chunks": chunks,
        "artifacts": artifacts,
    }


def fetch_artifact_rows(database_url: str, corpus_version: str) -> list[dict[str, Any]]:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_type, bucket, object_key, sha256, size_bytes, source_path, created_at
                FROM artifact_objects
                WHERE corpus_version = %s
                ORDER BY artifact_type, object_key
                """,
                (corpus_version,),
            )
            rows = cursor.fetchall()
    return [
        {
            "artifact_type": row[0],
            "bucket": row[1],
            "object_key": row[2],
            "sha256": row[3],
            "size_bytes": row[4],
            "source_path": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]
```

- [x] **Step 5: Run verifier tests**

Run:

```powershell
pytest tests\test_cloud_verify_import.py tests\test_cloud_postgres.py -q
```

Expected: PASS.

- [x] **Step 6: Run the live verifier locally**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
python scripts\cloud\verify_cloud_import.py --corpus-version 2026-05-22-initial
```

Expected: JSON with `"ok": true`.

---

### Task 2: Qdrant Snapshot Artifact

**Files:**
- Create: `scripts/cloud/qdrant_snapshot.py`
- Create: `tests/test_cloud_qdrant_snapshot.py`
- Modify: `scripts/cloud/postgres.py`

- [x] **Step 1: Write failing tests for snapshot planning**

Add `tests/test_cloud_qdrant_snapshot.py`:

```python
import zipfile
from pathlib import Path

from scripts.cloud.qdrant_snapshot import create_qdrant_zip, qdrant_artifact_key


def test_qdrant_artifact_key_uses_vector_index_prefix():
    assert qdrant_artifact_key("2026-05-22-initial") == "vector-index/2026-05-22-initial/qdrant.zip"


def test_create_qdrant_zip_includes_nested_files(tmp_path: Path):
    source = tmp_path / "vector_db" / "qdrant"
    nested = source / "collections" / "geo"
    nested.mkdir(parents=True)
    (nested / "data.bin").write_bytes(b"abc")
    output = tmp_path / "out" / "qdrant.zip"

    create_qdrant_zip(source, output)

    with zipfile.ZipFile(output, "r") as archive:
        assert archive.namelist() == ["collections/geo/data.bin"]
        assert archive.read("collections/geo/data.bin") == b"abc"
```

- [x] **Step 2: Run the focused failing test**

Run:

```powershell
pytest tests\test_cloud_qdrant_snapshot.py -q
```

Expected: FAIL because `scripts.cloud.qdrant_snapshot` does not exist.

- [x] **Step 3: Implement snapshot creation**

Create `scripts/cloud/qdrant_snapshot.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.config import CloudConfig
from scripts.cloud.postgres import register_artifact_objects
from scripts.cloud.s3_artifacts import build_artifact_record, upload_artifact


def qdrant_artifact_key(corpus_version: str) -> str:
    return f"vector-index/{corpus_version}/qdrant.zip"


def create_qdrant_zip(source_dir: Path, output_path: Path) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"Qdrant directory not found: {source_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())


def build_qdrant_artifact(*, corpus_version: str, zip_path: Path) -> dict[str, Any]:
    record = build_artifact_record(
        artifact_type="qdrant_snapshot",
        corpus_version=corpus_version,
        path=zip_path,
        prefix="vector-index",
    )
    return {**record, "object_key": qdrant_artifact_key(corpus_version)}


def run_snapshot(
    *,
    corpus_version: str,
    source_dir: Path,
    output_path: Path,
    execute: bool,
) -> dict[str, Any]:
    create_qdrant_zip(source_dir, output_path)
    record = build_qdrant_artifact(corpus_version=corpus_version, zip_path=output_path)
    if not execute:
        return {"status": "dry_run", "artifact": record}
    config = CloudConfig.from_env()
    uploaded = upload_artifact(bucket=config.s3_bucket, region=config.aws_region, record=record)
    register_artifact_objects(config.database_url, [uploaded])
    return {"status": "uploaded", "artifact": uploaded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a rebuildable Qdrant snapshot artifact to S3.")
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--source-dir", default="vector_db/qdrant")
    parser.add_argument("--output", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output = Path(args.output) if args.output else Path("output") / "cloud" / args.corpus_version / "qdrant.zip"
    result = run_snapshot(
        corpus_version=args.corpus_version,
        source_dir=Path(args.source_dir),
        output_path=output,
        execute=args.execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Extract artifact registration**

Modify `scripts/cloud/postgres.py` by adding:

```python
def register_artifact_objects(database_url: str, artifacts: list[dict[str, Any]]) -> None:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            _execute_many(
                cursor,
                """
                INSERT INTO artifact_objects (
                  corpus_version, artifact_type, bucket, object_key,
                  sha256, size_bytes, source_path, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (corpus_version, artifact_type, object_key) DO UPDATE SET
                  bucket = EXCLUDED.bucket,
                  sha256 = EXCLUDED.sha256,
                  size_bytes = EXCLUDED.size_bytes,
                  source_path = EXCLUDED.source_path,
                  created_at = EXCLUDED.created_at
                """,
                (
                    (
                        artifact.get("corpus_version"),
                        artifact.get("artifact_type"),
                        artifact.get("bucket"),
                        artifact.get("object_key"),
                        artifact.get("sha256"),
                        artifact.get("size_bytes"),
                        artifact.get("source_path"),
                        artifact.get("created_at"),
                    )
                    for artifact in artifacts
                ),
            )
        connection.commit()
```

Then replace the duplicated artifact insert block inside `upsert_core_corpus` with:

```python
            _execute_many(
                cursor,
                """
                INSERT INTO artifact_objects (
                  corpus_version, artifact_type, bucket, object_key,
                  sha256, size_bytes, source_path, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (corpus_version, artifact_type, object_key) DO UPDATE SET
                  bucket = EXCLUDED.bucket,
                  sha256 = EXCLUDED.sha256,
                  size_bytes = EXCLUDED.size_bytes,
                  source_path = EXCLUDED.source_path,
                  created_at = EXCLUDED.created_at
                """,
                (
                    (
                        artifact.get("corpus_version"),
                        artifact.get("artifact_type"),
                        artifact.get("bucket"),
                        artifact.get("object_key"),
                        artifact.get("sha256"),
                        artifact.get("size_bytes"),
                        artifact.get("source_path"),
                        artifact.get("created_at"),
                    )
                    for artifact in artifacts
                ),
            )
```

If extracting the duplicate block introduces too much churn, keep the existing block and use `register_artifact_objects` only for the new snapshot command.

- [x] **Step 5: Run snapshot tests**

Run:

```powershell
pytest tests\test_cloud_qdrant_snapshot.py tests\test_cloud_import_corpus.py tests\test_cloud_postgres.py -q
```

Expected: PASS.

- [x] **Step 6: Upload the live Qdrant snapshot**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
python scripts\cloud\qdrant_snapshot.py --corpus-version 2026-05-22-initial --execute
```

Expected: status `"uploaded"` and an S3 object key `vector-index/2026-05-22-initial/qdrant.zip`.

---

### Task 3: Stratified Quick Seed Sampling

**Files:**
- Modify: `scripts/seed_api_queries.py`
- Modify: `tests/test_seed_api_queries.py`
- Modify: `scripts/run_full_api_parallel_with_watch.ps1`
- Modify: `tests/test_full_api_parallel_with_watch.py`

- [ ] **Step 1: Write failing test for stratified selection**

Append to `tests/test_seed_api_queries.py`:

```python
from scripts.seed_api_queries import select_queries_for_model


def test_select_queries_for_model_can_stratify_by_persona_and_stage(tmp_path: Path):
    seed_run = tmp_path / "seed"
    seed_run.mkdir()
    (seed_run / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,query,target_brand,persona,journey_stage,scenario_provider,scenario_model,api_status,notes",
                "q001,A,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
                "q002,B,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
                "q003,C,AlphaXXXX,founder,vendor,openrouter,openai/gpt-4.1-mini,success,old",
                "q004,D,AlphaXXXX,founder,vendor,openrouter,openai/gpt-4.1-mini,success,old",
                "q005,E,AlphaXXXX,agency,compare,openrouter,openai/gpt-4.1-mini,success,old",
            ]
        ),
        encoding="utf-8",
    )

    rows = select_queries_for_model(seed_run, "openai/gpt-4.1-mini", limit=3, selection="stratified")

    assert [row["query_id"] for row in rows] == ["q001", "q003", "q005"]
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
pytest tests\test_seed_api_queries.py::test_select_queries_for_model_can_stratify_by_persona_and_stage -q
```

Expected: FAIL because `selection` is not supported.

- [ ] **Step 3: Implement stratified selector**

Modify `scripts/seed_api_queries.py`:

```python
def stratify_rows(rows: list[dict[str, str]], limit: int | None) -> list[dict[str, str]]:
    if limit is None or len(rows) <= limit:
        return rows
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("persona", ""), row.get("journey_stage", ""))
        groups.setdefault(key, []).append(row)
    selected: list[dict[str, str]] = []
    while len(selected) < limit and groups:
        for key in sorted(list(groups)):
            bucket = groups[key]
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) == limit:
                    break
            if not bucket:
                groups.pop(key, None)
    return selected
```

Change `select_queries_for_model` to:

```python
def select_queries_for_model(
    seed_run_dir: Path,
    model: str,
    limit: int | None = None,
    selection: str = "row_order",
) -> list[dict[str, str]]:
    rows = read_query_rows(seed_run_dir)
    selected = [row for row in rows if row.get("scenario_model") == model]
    if selection == "stratified":
        selected = stratify_rows(selected, limit)
    elif limit is not None:
        selected = selected[:limit]
    if selection not in {"row_order", "stratified"}:
        raise ValueError(f"Unknown seed selection mode: {selection}")
    return [{field: str(row.get(field, "")) for field in QUERY_FIELDS} for row in selected]
```

Change `seed_queries_for_model` to accept and pass `selection`:

```python
def seed_queries_for_model(
    seed_run_dir: Path,
    model: str,
    output_dir: Path,
    limit: int | None = None,
    selection: str = "row_order",
) -> int:
    rows = select_queries_for_model(seed_run_dir, model, limit=limit, selection=selection)
```

Add CLI argument:

```python
parser.add_argument("--selection", choices=["row_order", "stratified"], default="row_order")
```

Pass it in `main`:

```python
count = seed_queries_for_model(
    Path(args.seed_run_dir),
    args.model,
    Path(args.output_dir),
    limit=args.limit,
    selection=args.selection,
)
```

- [ ] **Step 4: Wire quick mode to stratified selection**

Modify `scripts/run_full_api_parallel_with_watch.ps1` near the run mode setup:

```powershell
$SeedSelection = if ($RunMode -eq "quick") { "stratified" } else { "row_order" }
```

Add to `$seedArgs` in `Write-SeedQueries`:

```powershell
"--selection", $SeedSelection
```

Add to dry-run output when `$SeedQueriesRunDir` is set:

```powershell
Write-Host "Seed selection: $SeedSelection"
```

- [ ] **Step 5: Update PowerShell dry-run test**

Modify `tests/test_full_api_parallel_with_watch.py` in the seed dry-run assertion block to include:

```python
assert "Seed selection: stratified" in result.stdout
```

- [ ] **Step 6: Run seed and runner tests**

Run:

```powershell
pytest tests\test_seed_api_queries.py tests\test_full_api_parallel_with_watch.py -q
```

Expected: PASS.

---

### Task 4: Cloud Operations Runbook

**Files:**
- Create: `docs/cloud-operations.md`
- Modify: `docs/architecture.md`
- Modify: `docs/risks.md`
- Modify: `docs/next.md`

- [ ] **Step 1: Create the runbook**

Create `docs/cloud-operations.md`:

```markdown
# Cloud Operations

## Current AWS Resources

- S3 bucket: `geo-resource-library-prod-940329548423-ap-northeast-1-an`
- Region: `ap-northeast-1`
- RDS identifier: `geo-postgres-prod`
- RDS endpoint: `geo-postgres-prod.cbkgwuwamngl.ap-northeast-1.rds.amazonaws.com`
- Default corpus version: `2026-05-22-initial`

## Credential Rules

- Do not store root user access keys in `.env`.
- Use an IAM user access key for local import and snapshot commands.
- Keep `.env` untracked.
- After replacing a key, verify S3 list, put, head, and delete before deleting the old key.

## Verify Cloud Import

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
python scripts\cloud\verify_cloud_import.py --corpus-version 2026-05-22-initial
```

The command should return `"ok": true`.

## Upload Core Corpus

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
python scripts\cloud\import_corpus.py --corpus-version 2026-05-22-initial --allow-quality-issues --execute
```

Use a new corpus version when the source corpus changes.

## Upload Qdrant Snapshot

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
python scripts\cloud\qdrant_snapshot.py --corpus-version 2026-05-22-initial --execute
```

Qdrant is not the source of truth. The snapshot is a convenience artifact and can be rebuilt from versioned chunks.

## Quick Seeded Benchmark

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -RunMode quick -SeedQueriesRunDir runs\client_acquisition_simulator_full_api_20260517_200716
```

Quick mode should use stratified seeded sampling after the cloud operations hardening work is complete.
```

- [ ] **Step 2: Update architecture note**

Add one bullet under `## Modules` in `docs/architecture.md`:

```markdown
- `scripts/cloud/verify_cloud_import.py` and `scripts/cloud/qdrant_snapshot.py`: operational cloud commands for verifying imported corpus versions and storing rebuildable Qdrant snapshots in S3.
```

Add one line under `## Boundaries`:

```markdown
- Cloud operation commands must remain explicit user-run scripts; they should not silently upload local artifacts during crawler, chunking, or benchmark runs.
```

- [ ] **Step 3: Update risk note**

Add under `## Operational Risks` in `docs/risks.md`:

```markdown
- Qdrant snapshots in S3 are convenience restore artifacts, not authoritative data. A stale snapshot must not override a newer `chunks.jsonl` corpus version.
```

- [ ] **Step 4: Update next steps**

In `docs/next.md`, move these items to `Done` after implementation:

```markdown
- Replaced root AWS access keys with an IAM user key and verified S3 list, write, head, and delete against the project bucket.
- Added a repeatable cloud import verifier for RDS counts and S3 artifact sizes.
- Added Qdrant snapshot upload as a rebuildable S3 artifact.
- Added stratified seed sampling for quick seeded benchmark runs.
```

Add these items to `Next`:

```markdown
1. Delete the deactivated root access key after one more successful project run with the IAM key.
2. Review or refresh the 4 replacement-character source rows before the next clean corpus version.
3. Run a quick seeded benchmark with stratified sampling, then compare AlphaXXXX movement against the previous baseline.
```

- [ ] **Step 5: Run the full local suite**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

---

## Execution Order

1. Task 1 gives the project a reliable cloud health check.
2. Task 2 stores Qdrant as an optional rebuildable artifact after the authoritative corpus is verified.
3. Task 3 fixes the highest-impact benchmark quality issue currently documented for quick runs.
4. Task 4 records the runbook and updates project memory so future work stays aligned.

## Self-Review

- Spec coverage: The plan covers post-root-key cleanup, repeatable cloud verification, Qdrant snapshot handling, quick benchmark sampling quality, and documentation.
- Placeholder scan: No task uses TBD, TODO, or unspecified "add tests" language.
- Type consistency: Function names introduced in tests match the implementation snippets: `build_verification_result`, `create_qdrant_zip`, `qdrant_artifact_key`, and `select_queries_for_model`.
