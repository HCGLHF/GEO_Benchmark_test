from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._common import read_jsonl
from scripts.build_keyword_index import build_keyword_artifact
from scripts.cloud.config import CloudConfig
from scripts.cloud.postgres import fetch_artifact_rows
from scripts.geo_eval.evidence_cards import build_evidence_card
from scripts.geo_eval.page_signals import tag_page


REQUIRED_ARTIFACTS = {
    "processed_documents": "documents.jsonl",
    "processed_chunks": "chunks.jsonl",
}


def _artifact_by_type(artifact_rows: list[dict[str, Any]], artifact_type: str) -> dict[str, Any]:
    matches = [row for row in artifact_rows if row.get("artifact_type") == artifact_type]
    if not matches:
        raise ValueError(f"Missing artifact type: {artifact_type}")
    return matches[0]


def _write_jsonl_dicts(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rebuild_local_artifacts(processed_dir: Path) -> dict[str, int | str]:
    documents = read_jsonl(processed_dir / "documents.jsonl")
    chunks = read_jsonl(processed_dir / "chunks.jsonl")
    signals = [tag_page(row) for row in documents]
    _write_jsonl_dicts(processed_dir / "page_signals.jsonl", signals)
    signal_by_url = {row.get("url"): row for row in signals}
    evidence_cards = [build_evidence_card(row, signal_by_url.get(row.get("url"), {})) for row in documents]
    _write_jsonl_dicts(processed_dir / "evidence_cards.jsonl", evidence_cards)
    with (processed_dir / "bm25_index.pkl").open("wb") as handle:
        pickle.dump(build_keyword_artifact(chunks), handle)
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "page_signals": len(signals),
        "evidence_cards": len(evidence_cards),
        "processed_dir": str(processed_dir),
    }


def download_processed_corpus(
    *,
    artifact_rows: list[dict[str, Any]],
    bucket: str,
    region: str,
    processed_dir: Path,
    s3_client: Any | None = None,
) -> dict[str, int | str]:
    if s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Install boto3 to download processed corpus artifacts.") from exc
        s3_client = boto3.client("s3", region_name=region)

    processed_dir.mkdir(parents=True, exist_ok=True)
    for artifact_type, filename in REQUIRED_ARTIFACTS.items():
        row = _artifact_by_type(artifact_rows, artifact_type)
        s3_client.download_file(str(row.get("bucket") or bucket), str(row["object_key"]), str(processed_dir / filename))

    return rebuild_local_artifacts(processed_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download cloud processed corpus files into local data/processed.")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--processed-dir", default="data/processed")
    args = parser.parse_args()
    config = CloudConfig.from_env()
    rows = fetch_artifact_rows(config.database_url, args.industry, args.corpus_version)
    result = download_processed_corpus(
        artifact_rows=rows,
        bucket=config.s3_bucket,
        region=config.aws_region,
        processed_dir=Path(args.processed_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
