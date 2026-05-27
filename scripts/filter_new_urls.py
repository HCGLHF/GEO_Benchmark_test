from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def filter_new_rows(
    rows: list[dict[str, str]],
    existing_pages: list[dict[str, str]],
    source_group: str | None = None,
) -> list[dict[str, str]]:
    existing_urls = {page.get("url", "") for page in existing_pages}
    return [
        row
        for row in rows
        if row.get("url", "") not in existing_urls
        and (not source_group or row.get("source_group") == source_group)
    ]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter a discovered URL inventory to URLs not already crawled.")
    parser.add_argument("--input", default="data/raw/discovered_urls.csv")
    parser.add_argument("--existing-pages", default="data/raw/pages.jsonl")
    parser.add_argument("--output", default="data/raw/new_urls_to_crawl.csv")
    parser.add_argument("--source-group", default=None)
    args = parser.parse_args()

    rows = read_csv(Path(args.input))
    existing_pages = read_jsonl(Path(args.existing_pages))
    filtered = filter_new_rows(rows, existing_pages, args.source_group)
    fields = list(rows[0].keys()) if rows else ["url"]
    write_csv(Path(args.output), filtered, fields)
    print(f"Wrote {len(filtered)} new URLs to {args.output}; skipped {len(rows) - len(filtered)} existing URLs")


if __name__ == "__main__":
    main()
