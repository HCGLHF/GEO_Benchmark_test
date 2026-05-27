# GEO Resource Library

This project builds a private retrieval and generation benchmark for GEO optimization. It crawls owned, competitor, and industry pages, then evaluates whether owned content is retrieved, mentioned, cited, and recommended by LLM-style answer systems.

## MVP Pipeline

1. Configure sources and queries.
2. Crawl pages with tiered fetch methods.
3. Clean pages into documents.
4. Chunk documents.
5. Build vector and keyword indexes.
6. Run retrieval evaluation.
7. Run generation evaluation.
8. Generate a Markdown report.

## Cloud Collaboration Model

The codebase is kept in Git. The resource-library data is kept outside Git:

- PostgreSQL on AWS RDS stores the queryable corpus and benchmark ledger.
- S3 stores large artifacts such as processed JSONL snapshots and future Qdrant snapshots.
- Local `.env`, raw data, run outputs, caches, and vector database files stay untracked.

Team members can clone the repository, configure their own `.env`, and verify access to the shared cloud corpus:

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

The setup script creates `.venv`, installs project dependencies, installs Playwright Chromium, and creates `.env` from `.env.example` only when `.env` does not already exist.

```powershell
python scripts\cloud\verify_cloud_import.py --industry geo-agency --corpus-version 2026-05-22-initial
```

For a new vertical, create the industry registry row before import:

```powershell
python scripts\cloud\create_industry.py --industry dental --display-name "Dental Clinics" --region AU --execute
```

Start with [docs/documentation-map.md](docs/documentation-map.md), then read [docs/cloud-database.md](docs/cloud-database.md) for the AWS/RDS/S3 setup.

## Local UI Console

Launch the local dashboard and dry-run planner:

```powershell
python -m scripts.ui_app.server --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. See [docs/ui-console.md](docs/ui-console.md) for scope and boundaries.
