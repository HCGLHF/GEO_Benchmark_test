from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.config import CloudConfig
from scripts.cloud.postgres import fetch_artifact_rows, fetch_corpus_counts


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


def head_artifacts(
    *,
    bucket: str,
    region: str,
    artifact_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
