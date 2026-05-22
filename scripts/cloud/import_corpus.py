from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._common import read_jsonl
from scripts.cloud.config import CloudConfig
from scripts.cloud.corpus_quality import audit_corpus
from scripts.cloud.postgres import execute_schema, upsert_core_corpus
from scripts.cloud.s3_artifacts import build_artifact_record, upload_artifact


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "sql" / "001_initial_schema.sql"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_import_plan(
    *,
    corpus_version: str,
    inventory_path: Path,
    documents_path: Path,
    chunks_path: Path,
) -> dict[str, Any]:
    inventory = read_csv(inventory_path)
    documents = read_jsonl(documents_path)
    chunks = read_jsonl(chunks_path)
    artifacts = [
        build_artifact_record(
            artifact_type="url_inventory",
            corpus_version=corpus_version,
            path=inventory_path,
            prefix="raw",
        ),
        build_artifact_record(
            artifact_type="processed_documents",
            corpus_version=corpus_version,
            path=documents_path,
            prefix="processed",
        ),
        build_artifact_record(
            artifact_type="processed_chunks",
            corpus_version=corpus_version,
            path=chunks_path,
            prefix="processed",
        ),
    ]
    return {
        "corpus_version": corpus_version,
        "inventory": inventory,
        "documents": documents,
        "chunks": chunks,
        "artifacts": artifacts,
        "quality_report": audit_corpus(inventory, documents, chunks),
        "row_counts": {
            "inventory_rows": len(inventory),
            "documents": len(documents),
            "chunks": len(chunks),
            "artifacts": len(artifacts),
        },
    }


def run_import(
    *,
    corpus_version: str,
    inventory_path: Path,
    documents_path: Path,
    chunks_path: Path,
    schema_path: Path,
    execute: bool,
    skip_s3: bool,
    skip_db: bool,
    allow_quality_issues: bool,
) -> dict[str, Any]:
    plan = build_import_plan(
        corpus_version=corpus_version,
        inventory_path=inventory_path,
        documents_path=documents_path,
        chunks_path=chunks_path,
    )
    if not plan["quality_report"]["is_import_safe"] and not allow_quality_issues:
        return {**plan, "status": "blocked_by_quality"}
    if not execute:
        return {**plan, "status": "dry_run"}

    config = CloudConfig.from_env()
    uploaded_artifacts = plan["artifacts"]
    if not skip_s3:
        uploaded_artifacts = [
            upload_artifact(bucket=config.s3_bucket, region=config.aws_region, record=artifact)
            for artifact in plan["artifacts"]
        ]
    if not skip_db:
        execute_schema(config.database_url, schema_path)
        upsert_core_corpus(
            database_url=config.database_url,
            corpus_version=corpus_version,
            inventory=plan["inventory"],
            documents=plan["documents"],
            chunks=plan["chunks"],
            artifacts=uploaded_artifacts,
        )
    return {**plan, "artifacts": uploaded_artifacts, "status": "imported"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the core GEO corpus into PostgreSQL and S3.")
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--inventory", default="data/raw/url_inventory.csv")
    parser.add_argument("--documents", default="data/processed/documents.jsonl")
    parser.add_argument("--chunks", default="data/processed/chunks.jsonl")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--execute", action="store_true", help="Actually write to S3/PostgreSQL.")
    parser.add_argument("--skip-s3", action="store_true", help="Do not upload artifact files to S3.")
    parser.add_argument("--skip-db", action="store_true", help="Do not write rows to PostgreSQL.")
    parser.add_argument("--allow-quality-issues", action="store_true")
    args = parser.parse_args()

    result = run_import(
        corpus_version=args.corpus_version,
        inventory_path=Path(args.inventory),
        documents_path=Path(args.documents),
        chunks_path=Path(args.chunks),
        schema_path=Path(args.schema),
        execute=args.execute,
        skip_s3=args.skip_s3,
        skip_db=args.skip_db,
        allow_quality_issues=args.allow_quality_issues,
    )
    printable = {
        "status": result["status"],
        "corpus_version": result["corpus_version"],
        "row_counts": result["row_counts"],
        "quality_report": result["quality_report"],
        "artifacts": [
            {
                "artifact_type": artifact["artifact_type"],
                "object_key": artifact["object_key"],
                "sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
            }
            for artifact in result["artifacts"]
        ],
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
