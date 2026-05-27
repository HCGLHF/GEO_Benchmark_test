# Industry Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add industry-level isolation to the AWS-backed corpus store so future industry datasets do not mix.

**Architecture:** Keep one RDS database and one S3 bucket. Use `industry_id` in PostgreSQL rows and `industries/{industry_id}/...` in S3 object keys. Require cloud commands to pass `--industry`.

**Tech Stack:** Python, pytest, PostgreSQL, S3, PowerShell.

---

### Task 1: Industry-Aware Artifact Keys

**Files:**
- Modify: `scripts/cloud/s3_artifacts.py`
- Modify: `scripts/cloud/import_corpus.py`
- Modify: `scripts/cloud/qdrant_snapshot.py`
- Test: `tests/test_cloud_import_corpus.py`
- Test: `tests/test_cloud_qdrant_snapshot.py`

- [x] Write tests expecting `industries/geo-agency/...` object keys.
- [x] Add `scripts/cloud/industry.py` with slug validation.
- [x] Pass `industry_id` into artifact records and Qdrant snapshot keys.
- [x] Require `--industry` in cloud import and snapshot commands.

### Task 2: PostgreSQL Industry Filters

**Files:**
- Modify: `scripts/cloud/postgres.py`
- Modify: `scripts/cloud/verify_cloud_import.py`
- Test: `tests/test_cloud_postgres.py`
- Test: `tests/test_cloud_verify_import.py`

- [x] Update read helpers to filter by `industry_id` and `corpus_version`.
- [x] Update write helpers to upsert `industries` and write `industry_id`.
- [x] Require `--industry` in cloud verification.

### Task 3: Migration SQL

**Files:**
- Create: `sql/002_industry_isolation.sql`
- Modify: `sql/001_initial_schema.sql`
- Test: `tests/test_cloud_schema.py`

- [x] Add `industries`.
- [x] Add and backfill `industry_id` columns.
- [x] Replace core versioned table keys with industry-aware keys.
- [x] Add composite foreign keys and industry-aware indexes.

### Task 4: Live Migration And Verification

**Files:**
- Modify: `docs/cloud-database.md`
- Modify: `docs/architecture.md`
- Modify: `docs/risks.md`
- Modify: `docs/next.md`

- [x] Apply `sql/002_industry_isolation.sql` to RDS.
- [x] Verify `geo-agency/2026-05-22-initial`.
- [x] Re-upload core artifacts and Qdrant snapshot under `industries/geo-agency/...`.
- [x] Verify RDS/S3 consistency after migration.
- [x] Update documentation and project memory.

### Task 5: Industry Registry Command

**Files:**
- Create: `scripts/cloud/create_industry.py`
- Modify: `scripts/cloud/postgres.py`
- Test: `tests/test_cloud_create_industry.py`
- Test: `tests/test_cloud_postgres.py`
- Modify: `docs/cloud-database.md`
- Modify: `docs/architecture.md`
- Modify: `docs/risks.md`
- Modify: `docs/next.md`

- [x] Add a dry-run-first CLI for creating or updating `industries` metadata rows.
- [x] Keep the command scoped to registry metadata only; imports and snapshots remain separate commands.
- [x] Document the new-industry workflow before corpus import.
