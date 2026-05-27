from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import read_jsonl, write_jsonl
from scripts.build_keyword_index import build_keyword_artifact


def is_llms_url(url: str) -> bool:
    parsed = urlparse(str(url))
    return parsed.path.rstrip("/").lower() == "/llms.txt"


def filter_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept = [row for row in rows if not is_llms_url(str(row.get("url", "")))]
    return kept, len(rows) - len(kept)


def write_keyword_index(chunks: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump(build_keyword_artifact(chunks), handle)


def write_variant_config(base_config_path: Path, output_config_path: Path, output_dir: Path) -> None:
    with base_config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    retrieval = dict(config.get("retrieval") or {})
    retrieval["documents"] = str(output_dir / "documents.jsonl")
    retrieval["chunks"] = str(output_dir / "chunks.jsonl")
    retrieval["keyword_index"] = str(output_dir / "bm25_index.pkl")
    retrieval["evidence_cards"] = str(output_dir / "evidence_cards.jsonl")
    retrieval["page_signals"] = str(output_dir / "page_signals.jsonl")
    config["retrieval"] = retrieval
    config.setdefault("run", {})
    config["run"]["corpus_variant"] = "without_llms"
    output_config_path.parent.mkdir(parents=True, exist_ok=True)
    output_config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def build_without_llms_variant(
    source_processed_dir: Path,
    output_dir: Path,
    base_config_path: Path,
    output_config_path: Path,
) -> dict[str, Any]:
    documents, removed_documents = filter_rows(read_jsonl(source_processed_dir / "documents.jsonl"))
    chunks, removed_chunks = filter_rows(read_jsonl(source_processed_dir / "chunks.jsonl"))
    page_signals, removed_page_signals = filter_rows(read_jsonl(source_processed_dir / "page_signals.jsonl"))
    evidence_cards, removed_evidence_cards = filter_rows(read_jsonl(source_processed_dir / "evidence_cards.jsonl"))

    write_jsonl(output_dir / "documents.jsonl", documents)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_jsonl(output_dir / "page_signals.jsonl", page_signals)
    write_jsonl(output_dir / "evidence_cards.jsonl", evidence_cards)
    write_keyword_index(chunks, output_dir / "bm25_index.pkl")
    write_variant_config(base_config_path, output_config_path, output_dir)

    manifest = {
        "variant": "without_llms",
        "source_processed_dir": str(source_processed_dir),
        "output_dir": str(output_dir),
        "documents": str(output_dir / "documents.jsonl"),
        "chunks": str(output_dir / "chunks.jsonl"),
        "page_signals": str(output_dir / "page_signals.jsonl"),
        "evidence_cards": str(output_dir / "evidence_cards.jsonl"),
        "keyword_index": str(output_dir / "bm25_index.pkl"),
        "config": str(output_config_path),
        "removed_documents": removed_documents,
        "removed_chunks": removed_chunks,
        "removed_page_signals": removed_page_signals,
        "removed_evidence_cards": removed_evidence_cards,
        "kept_documents": len(documents),
        "kept_chunks": len(chunks),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "variant_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a processed corpus variant that excludes /llms.txt.")
    parser.add_argument("--source-processed-dir", default="data/processed")
    parser.add_argument("--output-dir", default="data/experiments/without_llms/processed")
    parser.add_argument("--base-config", default="config/client_acquisition_simulator.yaml")
    parser.add_argument("--output-config", default="config/client_acquisition_simulator.without_llms.yaml")
    args = parser.parse_args()

    result = build_without_llms_variant(
        source_processed_dir=Path(args.source_processed_dir),
        output_dir=Path(args.output_dir),
        base_config_path=Path(args.base_config),
        output_config_path=Path(args.output_config),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
