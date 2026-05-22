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
