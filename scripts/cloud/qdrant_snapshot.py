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
from scripts.cloud.industry import normalize_industry_id
from scripts.cloud.postgres import register_artifact_objects
from scripts.cloud.s3_artifacts import build_artifact_record, upload_artifact


def qdrant_artifact_key(industry_id: str, corpus_version: str) -> str:
    clean_industry = normalize_industry_id(industry_id)
    return f"industries/{clean_industry}/vector-index/{corpus_version}/qdrant.zip"


def create_qdrant_zip(source_dir: Path, output_path: Path) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"Qdrant directory not found: {source_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())


def build_qdrant_artifact(*, industry_id: str, corpus_version: str, zip_path: Path) -> dict[str, Any]:
    clean_industry = normalize_industry_id(industry_id)
    record = build_artifact_record(
        industry_id=clean_industry,
        artifact_type="qdrant_snapshot",
        corpus_version=corpus_version,
        path=zip_path,
        prefix="vector-index",
    )
    return {**record, "object_key": qdrant_artifact_key(clean_industry, corpus_version)}


def run_snapshot(
    *,
    industry_id: str,
    corpus_version: str,
    source_dir: Path,
    output_path: Path,
    execute: bool,
) -> dict[str, Any]:
    clean_industry = normalize_industry_id(industry_id)
    create_qdrant_zip(source_dir, output_path)
    record = build_qdrant_artifact(
        industry_id=clean_industry,
        corpus_version=corpus_version,
        zip_path=output_path,
    )
    if not execute:
        return {"status": "dry_run", "artifact": record}
    config = CloudConfig.from_env()
    uploaded = upload_artifact(bucket=config.s3_bucket, region=config.aws_region, record=record)
    register_artifact_objects(config.database_url, [uploaded])
    return {"status": "uploaded", "artifact": uploaded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a rebuildable Qdrant snapshot artifact to S3.")
    parser.add_argument("--industry", required=True, help="Industry id such as geo-agency, dental, or real-estate.")
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--source-dir", default="vector_db/qdrant")
    parser.add_argument("--output", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    clean_industry = normalize_industry_id(args.industry)
    output = (
        Path(args.output)
        if args.output
        else Path("output") / "cloud" / clean_industry / args.corpus_version / "qdrant.zip"
    )
    result = run_snapshot(
        industry_id=clean_industry,
        corpus_version=args.corpus_version,
        source_dir=Path(args.source_dir),
        output_path=output,
        execute=args.execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
