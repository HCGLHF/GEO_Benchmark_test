from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts._common import utc_now_iso


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_key(prefix: str, corpus_version: str, path: Path) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{corpus_version}/{path.name}"


def build_artifact_record(
    *,
    artifact_type: str,
    corpus_version: str,
    path: Path,
    prefix: str,
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "corpus_version": corpus_version,
        "object_key": artifact_key(prefix, corpus_version, path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "source_path": str(path),
        "created_at": utc_now_iso(),
    }


def upload_artifact(
    *,
    bucket: str,
    region: str,
    record: dict[str, Any],
    s3_client: Any | None = None,
) -> dict[str, Any]:
    if s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Install boto3 to upload artifacts to S3.") from exc
        s3_client = boto3.client("s3", region_name=region)
    s3_client.upload_file(record["source_path"], bucket, record["object_key"])
    return {**record, "bucket": bucket}
