from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import read_jsonl, write_jsonl
from scripts.build_keyword_index import build_keyword_artifact
from scripts.chunk_documents import chunk_documents
from scripts.clean_documents import clean_pages
from scripts.geo_eval.evidence_cards import build_evidence_card
from scripts.geo_eval.page_signals import tag_page


def target_domain_matches(url: str, target_domain: str) -> bool:
    host = urlparse(str(url)).netloc.lower().removeprefix("www.")
    target = str(target_domain).lower().removeprefix("www.")
    return host == target


def replace_scope_matches(url: str, *, target_domain: str, replace_url_prefix: str | None = None) -> bool:
    if replace_url_prefix:
        return str(url).startswith(replace_url_prefix)
    return target_domain_matches(url, target_domain)


def _write_jsonl_dicts(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_keyword_index(chunks: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump(build_keyword_artifact(chunks), handle)


def refresh_owned_site_processed(
    *,
    raw_pages_path: Path,
    inventory_path: Path,
    processed_dir: Path,
    target_domain: str,
    replace_url_prefix: str | None = None,
) -> dict[str, Any]:
    documents_path = processed_dir / "documents.jsonl"
    chunks_path = processed_dir / "chunks.jsonl"
    signals_path = processed_dir / "page_signals.jsonl"
    evidence_path = processed_dir / "evidence_cards.jsonl"
    keyword_index_path = processed_dir / "bm25_index.pkl"

    existing_documents = read_jsonl(documents_path)
    incoming_documents = [doc.model_dump() for doc in clean_pages(raw_pages_path, inventory_path)]
    incoming_owned = [
        row for row in incoming_documents if target_domain_matches(str(row.get("url", "")), target_domain)
    ]
    kept_existing = [
        row
        for row in existing_documents
        if not replace_scope_matches(
            str(row.get("url", "")),
            target_domain=target_domain,
            replace_url_prefix=replace_url_prefix,
        )
    ]
    merged_documents = kept_existing + incoming_owned
    write_jsonl(documents_path, merged_documents)

    chunks = [chunk.model_dump() for chunk in chunk_documents(documents_path)]
    write_jsonl(chunks_path, chunks)

    signals = [tag_page(row) for row in merged_documents]
    _write_jsonl_dicts(signals_path, signals)
    signal_by_url = {row.get("url"): row for row in signals}
    evidence_cards = [build_evidence_card(row, signal_by_url.get(row.get("url"), {})) for row in merged_documents]
    _write_jsonl_dicts(evidence_path, evidence_cards)
    _write_keyword_index(chunks, keyword_index_path)

    result = {
        "processed_dir": str(processed_dir),
        "target_domain": target_domain,
        "replace_url_prefix": replace_url_prefix or "",
        "replaced_owned_documents": len(existing_documents) - len(kept_existing),
        "incoming_owned_documents": len(incoming_owned),
        "total_documents": len(merged_documents),
        "total_chunks": len(chunks),
        "documents": str(documents_path),
        "chunks": str(chunks_path),
        "page_signals": str(signals_path),
        "evidence_cards": str(evidence_path),
        "keyword_index": str(keyword_index_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace owned-site processed docs and rebuild retrieval artifacts.")
    parser.add_argument("--raw-pages", default="data/raw/alpha_update_pages.jsonl")
    parser.add_argument("--url-inventory", default="data/raw/alpha_update_discovered_urls.csv")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--target-domain", default="alphaxxxx.com")
    parser.add_argument("--replace-url-prefix", default="")
    args = parser.parse_args()
    refresh_owned_site_processed(
        raw_pages_path=Path(args.raw_pages),
        inventory_path=Path(args.url_inventory),
        processed_dir=Path(args.processed_dir),
        target_domain=args.target_domain,
        replace_url_prefix=args.replace_url_prefix or None,
    )


if __name__ == "__main__":
    main()
