# Cloud Database And Artifact Store

This project uses Git for code and documentation, and AWS for shared data. The database and large artifacts should not be committed to Git.

## Current Decision

- Git stores scripts, tests, configuration templates, documentation, and SQL schema.
- AWS RDS PostgreSQL stores the queryable corpus and benchmark ledger.
- AWS S3 stores versioned corpus artifacts and future vector-index snapshots.
- Local machines store `.env`, temporary caches, raw data, run outputs, and rebuilt Qdrant files.

This lets a team member in another location clone the repo, configure credentials, and work against the same shared corpus without copying local data directories through Git.

## AWS Resources

- AWS region: `ap-northeast-1`
- S3 bucket: `geo-resource-library-prod-940329548423-ap-northeast-1-an`
- RDS identifier: `geo-postgres-prod`
- RDS endpoint: `geo-postgres-prod.cbkgwuwamngl.ap-northeast-1.rds.amazonaws.com`
- RDS port: `5432`
- PostgreSQL database used so far: `postgres`
- PostgreSQL admin user used so far: `geo_admin`
- Current corpus version: `2026-05-22-initial`

These identifiers are not passwords. Do not commit the real `DATABASE_URL` password, AWS access key, or AWS secret access key.

## Environment Variables

Copy `.env.example` to `.env` and fill in local-only secrets:

```env
AWS_REGION=ap-northeast-1
AWS_DEFAULT_REGION=ap-northeast-1
S3_BUCKET=geo-resource-library-prod-940329548423-ap-northeast-1-an
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
DATABASE_URL=postgresql://USER:PASSWORD@geo-postgres-prod.cbkgwuwamngl.ap-northeast-1.rds.amazonaws.com:5432/postgres?sslmode=require
```

Use an IAM user key for project operations. Do not use a root user access key in `.env`.

## Current Imported Corpus

Corpus version `2026-05-22-initial` has been imported and verified:

- `url_inventory`: 1,683 rows
- `documents`: 1,683 rows
- `chunks`: 6,225 rows
- `artifact_objects`: 3 rows

Registered S3 artifacts:

- `raw/2026-05-22-initial/url_inventory.csv`
- `processed/2026-05-22-initial/documents.jsonl`
- `processed/2026-05-22-initial/chunks.jsonl`
- `vector-index/2026-05-22-initial/qdrant.zip`

## PostgreSQL Tables

The schema lives in `sql/001_initial_schema.sql`.

- `corpus_versions`: one row per imported corpus version with inventory, document, and chunk counts.
- `artifact_objects`: S3 object registry with bucket, object key, hash, size, and source path.
- `url_inventory`: versioned source URL inventory and crawl metadata.
- `documents`: cleaned page-level corpus records.
- `chunks`: retrieval chunks linked to documents.
- `query_sets` and `queries`: versioned evaluation question sets.
- `benchmark_runs`: benchmark run metadata linked to corpus and query versions.
- `retrieval_results`: retrieval-level brand visibility and matched chunk details.
- `generation_results`: answer-level mention, citation, recommendation, and coverage metrics.
- `model_call_attempts`: model-call audit trail.
- `llm_call_cache`: cache table for model responses when that path is promoted to cloud storage.

## S3 Responsibilities

S3 is the artifact store, not the query database. Store large files and snapshots there, then register their object keys and hashes in PostgreSQL.

Current artifact types:

- `url_inventory`
- `processed_documents`
- `processed_chunks`
- `qdrant_snapshot`

## Qdrant Responsibilities

Qdrant remains a rebuildable retrieval index. It should not go into Git and should not be treated as the source of truth.

The source of truth is:

1. `documents` and `chunks` in PostgreSQL for queryable rows.
2. Versioned JSONL artifacts in S3 for reproducible snapshots.
3. Local or S3 snapshot copies of Qdrant only for faster restore.

Current Qdrant snapshot:

- S3 key: `vector-index/2026-05-22-initial/qdrant.zip`
- Size: 18,150,632 bytes
- SHA-256: `e840f1ab05f44e7f11cc3118788237f2a4b991a17bc03ebb00219993ac6b9e87`

## Team Onboarding

1. Clone the Git repository.
2. Create a local `.env` from `.env.example`.
3. Ask the AWS admin to allowlist the team member's current public IP for RDS access, or connect through the approved VPN/bastion path.
4. Use an IAM user key with the project S3 permissions.
5. Run the cloud verifier:

```powershell
python scripts\cloud\verify_cloud_import.py --corpus-version 2026-05-22-initial
```

If using the project-local cloud dependency directory on the original workstation, set:

```powershell
$env:PYTHONPATH=(Resolve-Path .deps\cloud).Path
```

A normal developer setup can instead install project dependencies from `pyproject.toml`.

## Update Workflow

Use a new `corpus_version` when the resource library changes:

```text
2026-05-22-initial
2026-06-01-refresh
2026-06-15-alpha-content-update
```

Do not overwrite an old corpus version for a new business experiment. Import a new version and compare runs against explicit corpus versions.

Import command:

```powershell
python scripts\cloud\import_corpus.py --corpus-version 2026-05-22-initial --allow-quality-issues --execute
```

Verification command:

```powershell
python scripts\cloud\verify_cloud_import.py --corpus-version 2026-05-22-initial
```

## Security Notes

- `.env` is ignored and must stay local.
- Root access keys should stay deleted or disabled.
- RDS inbound access should be restricted to specific IPs or a controlled network path.
- Team members should receive the narrowest IAM and PostgreSQL permissions that fit their role.
- Do not paste secrets into GitHub issues, PRs, docs, chat, or committed logs.
