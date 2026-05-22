# Industry Isolation Design

## Goal

Support multiple unrelated industry corpora in the same AWS-backed resource library without mixing documents, chunks, scenarios, benchmark runs, or S3 artifacts.

## Decision

Use one RDS PostgreSQL database and one S3 bucket, with explicit `industry_id` isolation:

- PostgreSQL rows are filtered by `industry_id` first.
- S3 object keys use `industries/{industry_id}/...`.
- Cloud CLI commands require `--industry`.
- Existing data is backfilled into `geo-agency`.

## Industry IDs

Industry ids are lowercase slugs such as `geo-agency`, `dental`, `real-estate`, or `legal`.

They must:

- be lowercase
- use letters, numbers, and hyphens only
- start and end with a letter or number
- be 3-64 characters long

## PostgreSQL Shape

`sql/002_industry_isolation.sql` adds:

- `industries`
- `industry_id` columns on corpus, artifact, query, run, result, attempt, and cache tables
- composite primary keys for versioned corpus and query tables
- composite foreign keys so `industry_id + corpus_version` and `industry_id + query_set_version` stay together

## S3 Shape

New artifact keys use:

```text
industries/{industry_id}/raw/{corpus_version}/url_inventory.csv
industries/{industry_id}/processed/{corpus_version}/documents.jsonl
industries/{industry_id}/processed/{corpus_version}/chunks.jsonl
industries/{industry_id}/vector-index/{corpus_version}/qdrant.zip
```

Legacy root-level keys for `geo-agency/2026-05-22-initial` remain registered for compatibility, but new tools should prefer industry-prefixed keys.

## Commands

```powershell
python scripts\cloud\create_industry.py --industry geo-agency --display-name "GEO / AI Visibility Agencies" --region Global --execute
python scripts\cloud\import_corpus.py --industry geo-agency --corpus-version 2026-05-22-initial --allow-quality-issues --execute
python scripts\cloud\verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-22-initial
python scripts\cloud\qdrant_snapshot.py --industry geo-agency --corpus-version 2026-05-22-initial --execute
```

## Verification

The implemented migration was verified against RDS for `geo-agency/2026-05-22-initial`:

- 1,683 URL inventory rows
- 1,683 documents
- 6,225 chunks
- 8 S3 artifact rows after registering both legacy and industry-prefixed artifacts
