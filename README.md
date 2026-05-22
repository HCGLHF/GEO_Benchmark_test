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
python scripts\cloud\verify_cloud_import.py --corpus-version 2026-05-22-initial
```

Start with [docs/documentation-map.md](docs/documentation-map.md), then read [docs/cloud-database.md](docs/cloud-database.md) for the AWS/RDS/S3 setup.
