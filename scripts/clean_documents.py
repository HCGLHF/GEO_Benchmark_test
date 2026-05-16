from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import DocumentRecord, content_hash, read_jsonl, stable_id, write_jsonl


def load_inventory(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["url"]: row for row in csv.DictReader(handle)}


def title_from_markdown(markdown: str, fallback_url: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return urlparse(fallback_url).path.strip("/") or fallback_url


def clean_pages(raw_pages_path: Path, inventory_path: Path) -> list[DocumentRecord]:
    inventory = load_inventory(inventory_path)
    documents: list[DocumentRecord] = []
    for raw in read_jsonl(raw_pages_path):
        url = raw["url"]
        meta = inventory.get(url, {})
        content = (raw.get("markdown") or "").strip()
        if not content:
            continue
        documents.append(
            DocumentRecord(
                document_id=stable_id("doc", url),
                url=url,
                site=urlparse(url).netloc,
                brand=meta.get("brand", ""),
                title=title_from_markdown(content, url),
                description=None,
                content=content,
                source_type=meta.get("source_type", ""),
                page_type="unknown",
                collected_at=raw.get("collected_at", ""),
                content_hash=content_hash(content),
            )
        )
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw pages into document records.")
    parser.add_argument("--input", default="data/raw/pages.jsonl")
    parser.add_argument("--url-inventory", default="data/raw/url_inventory.csv")
    parser.add_argument("--output", default="data/processed/documents.jsonl")
    args = parser.parse_args()

    documents = clean_pages(Path(args.input), Path(args.url_inventory))
    write_jsonl(Path(args.output), documents)
    print(f"Wrote {len(documents)} documents to {args.output}")


if __name__ == "__main__":
    main()
