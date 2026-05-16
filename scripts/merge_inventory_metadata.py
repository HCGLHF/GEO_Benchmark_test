from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "url",
    "brand",
    "source_type",
    "source_group",
    "seed_url",
    "discovery_method",
    "depth",
    "status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def merge_inventory_with_documents(
    inventory_rows: list[dict[str, str]], document_rows: list[dict]
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in inventory_rows:
        url = row.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append({field: str(row.get(field, "")) for field in FIELDS})

    for doc in document_rows:
        url = str(doc.get("url", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(
            {
                "url": url,
                "brand": str(doc.get("brand", "")),
                "source_type": str(doc.get("source_type", "")),
                "source_group": "existing_documents",
                "seed_url": url,
                "discovery_method": "existing_document",
                "depth": "0",
                "status": "discovered",
            }
        )
    return merged


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge discovered URL inventory with existing document metadata.")
    parser.add_argument("--inventory", default="data/raw/discovered_urls.csv")
    parser.add_argument("--documents", default="data/processed/documents.jsonl")
    parser.add_argument("--output", default="data/raw/discovered_urls_enriched.csv")
    args = parser.parse_args()

    merged = merge_inventory_with_documents(read_csv(Path(args.inventory)), read_jsonl(Path(args.documents)))
    write_csv(Path(args.output), merged)
    print(f"Wrote {len(merged)} enriched inventory rows to {args.output}")


if __name__ == "__main__":
    main()
