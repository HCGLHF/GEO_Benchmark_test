# Cloud Database And Artifact Store

This project uses Git for code and documentation, and AWS for shared data. The database and large artifacts should not be committed to Git.

## Current Decision

- Git stores scripts, tests, configuration templates, documentation, and SQL schema.
- AWS RDS PostgreSQL stores the queryable corpus and benchmark ledger.
- AWS S3 stores versioned corpus artifacts and future vector-index snapshots.
- Local machines store `.env`, temporary caches, raw data, run outputs, and rebuilt Qdrant files.
- Every cloud row and new S3 artifact belongs to an explicit `industry_id`.

This lets a team member in another location clone the repo, configure credentials, and work against the same shared corpus without copying local data directories through Git.

## AWS Resources

- AWS region: `ap-northeast-1`
- S3 bucket: `geo-resource-library-prod-940329548423-ap-northeast-1-an`
- RDS identifier: `geo-postgres-prod`
- RDS endpoint: `geo-postgres-prod.cbkgwuwamngl.ap-northeast-1.rds.amazonaws.com`
- RDS port: `5432`
- PostgreSQL database used so far: `postgres`
- PostgreSQL admin user used so far: `geo_admin`
- Default industry id: `geo-agency`
- Current corpus version: `2026-05-27-alpha-refresh`

These identifiers are not passwords. Do not commit the real `DATABASE_URL` password, AWS access key, or AWS secret access key.

## Internal EC2 Server

An internal EC2 application host now runs the local UI console for server-side operations:

- Instance name: `resourcepool-gen-internal-01`
- Instance id: `i-0d947bb2cd6285cd2`
- Region: `ap-northeast-1`
- Instance type: `t3.xlarge`
- Project path: `/opt/resourcepool/Resourcepool_Gen`
- UI service: `resourcepool-ui.service`
- UI bind address: `127.0.0.1:8765`
- Admin browser entry: `https://admin.alphaxxxx.com/`
- Access layer: Cloudflare Access application `GEO Admin Console`
- Tunnel: Cloudflare Tunnel `resourcepool-admin-ec2`

The UI is intentionally not exposed directly to the public internet. Team browser access goes through Cloudflare Access and Cloudflare Tunnel; operators can still use the SSH tunnel command for direct maintenance. See `docs/ec2-server-runbook.md` for access, service management, and verification steps.

The RDS security group allows PostgreSQL `5432` from the EC2 application security group `sg-09c1d2510694af21f`. This is a security-group source allow rule, not a broad CIDR rule.

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

Corpus version `2026-05-27-alpha-refresh` has been imported and verified:

- `url_inventory`: 1,683 rows
- `documents`: 1,705 rows
- `chunks`: 6,283 rows
- `AlphaXXXX documents`: 59 rows
- `AlphaXXXX chunks`: 111 rows
- `artifact_objects`: 51 rows, including 4 corpus/vector artifacts and 47 current UI quick/standard report artifacts

Registered S3 artifacts:

- `industries/geo-agency/raw/2026-05-27-alpha-refresh/url_inventory.csv`
- `industries/geo-agency/processed/2026-05-27-alpha-refresh/documents.jsonl`
- `industries/geo-agency/processed/2026-05-27-alpha-refresh/chunks.jsonl`
- `industries/geo-agency/vector-index/2026-05-27-alpha-refresh/qdrant.zip`

The import used `--allow-quality-issues` for the same four known replacement-character rows already documented in the previous import: HornTech Chinese blog list content and SEOIndia homepage content. These rows are competitor/source data, not AlphaXXXX owned-site content, and should be refreshed in a later corpus cleanup.

Legacy pre-industry S3 artifacts are still registered for compatibility:

- `raw/2026-05-22-initial/url_inventory.csv`
- `processed/2026-05-22-initial/documents.jsonl`
- `processed/2026-05-22-initial/chunks.jsonl`
- `vector-index/2026-05-22-initial/qdrant.zip`

## Industry Isolation

Industry ids are lowercase slugs such as:

- `geo-agency`
- `dental`
- `real-estate`
- `legal`

Every cloud command must include `--industry`. PostgreSQL queries should filter by `industry_id` before filtering by `corpus_version`, `query_set_version`, or `run_id`.

New industries should be created deliberately before import. Do not reuse `geo-agency` for another industry just because the schema accepts it.

Create or update an industry registry row before importing that industry's corpus:

```powershell
python scripts\cloud\create_industry.py --industry dental --display-name "Dental Clinics" --region AU --notes "Dental services vertical" --execute
```

Omit `--execute` for a dry run. The command writes only the `industries` metadata row; it does not upload S3 artifacts or import documents/chunks.

## PostgreSQL Tables

The schema lives in `sql/001_initial_schema.sql`.

- `corpus_versions`: one row per imported corpus version with inventory, document, and chunk counts.
- `industries`: one row per isolated industry dataset, such as `geo-agency`, `dental`, or `real-estate`.
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

New artifact keys must use the industry prefix:

```text
industries/{industry_id}/raw/{corpus_version}/url_inventory.csv
industries/{industry_id}/processed/{corpus_version}/documents.jsonl
industries/{industry_id}/processed/{corpus_version}/chunks.jsonl
industries/{industry_id}/vector-index/{corpus_version}/qdrant.zip
```

Current artifact types:

- `url_inventory`
- `processed_documents`
- `processed_chunks`
- `qdrant_snapshot`

Run and report artifact types are also stored in S3 after a completed quick or standard benchmark:

- `run_manifest`
- `pipeline_state`
- `progress_html`
- `merge_manifest`
- `competitive_gap_report`
- `brand_performance_by_model`
- `dimension_breakdown`
- `retrieval_by_model`
- `model_answer_evaluations`
- `api_call_summary`
- `query_loss_analysis`
- `competitor_displacements`
- `page_optimization_plan`
- `owned_top5_pages`
- `owned_weak_pages`
- `retrieval_evidence_by_model`

Run artifact keys use:

```text
industries/{industry_id}/runs/{corpus_version}/{run_mode}/{run_id}/{section}/{filename}
```

Only `quick` and `standard` runs should be promoted to this shared run-artifact store. `test` runs are wiring checks and should stay local unless there is a specific debugging reason.

## Run Artifact Sync And Hydration

Git updates code only. Local data directories such as `data/` and `runs/` are intentionally ignored, so server updates must also hydrate artifacts from S3/RDS when the UI needs existing corpus files and report history.

Completed quick and standard run artifacts can be planned locally before upload:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel --run-mode quick --run-mode standard --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-22-initial --run-root runs\full_api_parallel_alpha_refresh_quick_final --run-mode quick --dry-run
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-27-alpha-refresh --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --dry-run
```

When the dry run looks correct, add `--execute` to upload artifacts to S3 and register them in PostgreSQL:

```powershell
python scripts\cloud\sync_run_artifacts.py --industry geo-agency --corpus-version 2026-05-27-alpha-refresh --run-root runs\full_api_parallel_ui --run-mode quick --run-mode standard --execute
```

The full API parallel runner can sync the current run automatically after a successful merge:

```powershell
python scripts\full_api_parallel_runner.py --run-mode quick --sync-artifacts --industry geo-agency --corpus-version 2026-05-27-alpha-refresh
```

To rebuild a server or a new developer checkout from the shared artifact store:

```powershell
python scripts\cloud\hydrate_artifacts.py --industry geo-agency --corpus-version 2026-05-27-alpha-refresh --run-mode quick --run-mode standard --project-root .
```

Hydration is non-destructive by default: existing local files are skipped, so a server that already has newer Phase 1 copied data will not be overwritten by older cloud corpus artifacts. Use `--overwrite` only when deliberately replacing local artifacts with cloud copies.

Hydrated run reports are restored under:

```text
runs/cloud_synced/{run_mode}/{run_id}/merged/
```

## Qdrant Responsibilities

Qdrant remains a rebuildable retrieval index. It should not go into Git and should not be treated as the source of truth.

The source of truth is:

1. `documents` and `chunks` in PostgreSQL for queryable rows.
2. Versioned JSONL artifacts in S3 for reproducible snapshots.
3. Local or S3 snapshot copies of Qdrant only for faster restore.

Current Qdrant snapshot:

- S3 key: `industries/geo-agency/vector-index/2026-05-27-alpha-refresh/qdrant.zip`
- Size: 18,150,632 bytes
- SHA-256: `e840f1ab05f44e7f11cc3118788237f2a4b991a17bc03ebb00219993ac6b9e87`

## Team Onboarding

1. Clone the Git repository.
2. Create a local `.env` from `.env.example`.
3. Ask the AWS admin to allowlist the team member's current public IP for RDS access, or connect through the approved VPN/bastion path.
4. Use an IAM user key with the project S3 permissions.
5. Run the cloud verifier:

```powershell
python scripts\cloud\verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-27-alpha-refresh
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
2026-05-27-alpha-refresh
2026-06-01-refresh
2026-06-15-alpha-content-update
```

Do not overwrite an old corpus version for a new business experiment. Import a new version and compare runs against explicit corpus versions.

For a new industry, create the registry row first:

```powershell
python scripts\cloud\create_industry.py --industry dental --display-name "Dental Clinics" --region AU --execute
```

Import command:

```powershell
python scripts\cloud\import_corpus.py --industry dental --corpus-version 2026-06-01-initial --allow-quality-issues --execute
```

Verification command:

```powershell
python scripts\cloud\verify_cloud_import.py --industry dental --corpus-version 2026-06-01-initial
```

Qdrant snapshot command:

```powershell
python scripts\cloud\qdrant_snapshot.py --industry dental --corpus-version 2026-06-01-initial --execute
```

## Security Notes

- `.env` is ignored and must stay local.
- Root access keys should stay deleted or disabled.
- RDS inbound access should be restricted to specific IPs or a controlled network path.
- Team members should receive the narrowest IAM and PostgreSQL permissions that fit their role.
- Do not paste secrets into GitHub issues, PRs, docs, chat, or committed logs.
