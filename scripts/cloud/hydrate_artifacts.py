from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.config import CloudConfig
from scripts.cloud.industry import normalize_industry_id
from scripts.cloud.postgres import fetch_artifact_rows


CORPUS_LOCAL_PATHS = {
    "url_inventory": Path("data/raw/url_inventory.csv"),
    "processed_documents": Path("data/processed/documents.jsonl"),
    "processed_chunks": Path("data/processed/chunks.jsonl"),
}
RUN_ROOT_SECTIONS = {"manifest": {"run_manifest.json"}, "logs": {"pipeline_state.jsonl"}, "ui": {"progress.html"}}
RUN_MERGED_SECTIONS = {"reports", "tables", "jsonl"}
RUN_MERGED_MANIFEST_FILES = {"merge_manifest.json"}


def _parts(object_key: str) -> list[str]:
    return [part for part in object_key.replace("\\", "/").split("/") if part]


def _run_key_parts(row: dict[str, Any]) -> tuple[str, str, str, str, str] | None:
    parts = _parts(str(row.get("object_key") or ""))
    if len(parts) < 8 or parts[0] != "industries" or parts[2] != "runs":
        return None
    run_mode, run_id, section, filename = parts[4], parts[5], parts[6], parts[7]
    return parts[3], run_mode, run_id, section, filename


def run_mode_for_artifact(row: dict[str, Any]) -> str | None:
    parsed = _run_key_parts(row)
    return parsed[1] if parsed else None


def local_path_for_artifact(row: dict[str, Any], project_root: Path) -> Path | None:
    artifact_type = str(row.get("artifact_type") or "")
    if artifact_type in CORPUS_LOCAL_PATHS:
        return project_root / CORPUS_LOCAL_PATHS[artifact_type]

    parsed = _run_key_parts(row)
    if parsed is None:
        return None
    _, run_mode, run_id, section, filename = parsed
    run_root = project_root / "runs" / "cloud_synced" / run_mode / run_id
    if section in RUN_ROOT_SECTIONS and filename in RUN_ROOT_SECTIONS[section]:
        return run_root / filename
    if section in RUN_MERGED_SECTIONS or (section == "manifest" and filename in RUN_MERGED_MANIFEST_FILES):
        return run_root / "merged" / filename
    return None


def _download_from_s3(bucket: str, object_key: str, destination: Path, region: str) -> None:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Install boto3 to hydrate artifacts from S3.") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    boto3.client("s3", region_name=region).download_file(bucket, object_key, str(destination))


def _keep_row(row: dict[str, Any], run_modes: set[str]) -> bool:
    mode = run_mode_for_artifact(row)
    if mode is None:
        return True
    return mode in run_modes


def hydrate_artifacts(
    *,
    artifact_rows: list[dict[str, Any]],
    project_root: Path,
    run_modes: set[str],
    download_fn: Callable[[str, str, Path], None] | None = None,
    region: str = "",
    default_bucket: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    downloaded: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    normalized_modes = {mode.lower() for mode in run_modes}
    for row in artifact_rows:
        if not _keep_row(row, normalized_modes):
            skipped.append({"object_key": str(row.get("object_key") or ""), "reason": "run_mode_filtered"})
            continue
        destination = local_path_for_artifact(row, project_root)
        if destination is None:
            skipped.append({"object_key": str(row.get("object_key") or ""), "reason": "unsupported_artifact"})
            continue
        if destination.exists() and not overwrite:
            skipped.append({"object_key": str(row.get("object_key") or ""), "reason": "exists"})
            continue
        bucket = str(row.get("bucket") or default_bucket)
        object_key = str(row.get("object_key") or "")
        if download_fn:
            download_fn(bucket, object_key, destination)
        else:
            _download_from_s3(bucket, object_key, destination, region=region)
        downloaded.append({"object_key": object_key, "local_path": str(destination)})
    return {
        "status": "hydrated",
        "summary": {"downloaded_count": len(downloaded), "skipped_count": len(skipped)},
        "downloaded": downloaded,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Hydrate corpus and run artifacts from S3/RDS onto this machine.")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--run-mode", action="append", choices=["quick", "standard"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--overwrite", action="store_true", help="Replace local artifacts that already exist.")
    args = parser.parse_args()
    clean_industry = normalize_industry_id(args.industry)
    config = CloudConfig.from_env(Path(args.project_root) / ".env")
    rows = fetch_artifact_rows(config.database_url, clean_industry, args.corpus_version)
    result = hydrate_artifacts(
        artifact_rows=rows,
        project_root=Path(args.project_root),
        run_modes=set(args.run_mode or ["quick", "standard"]),
        region=config.aws_region,
        default_bucket=config.s3_bucket,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
