from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def merge_by_url(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged_by_url = {page.get("url", ""): page for page in existing}
    for page in incoming:
        merged_by_url[page.get("url", "")] = page
    ordered_urls: list[str] = []
    seen: set[str] = set()
    for page in existing + incoming:
        url = page.get("url", "")
        if url and url not in seen:
            seen.add(url)
            ordered_urls.append(url)
    return [merged_by_url[url] for url in ordered_urls]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge raw page JSONL files by canonical URL.")
    parser.add_argument("--existing", default="data/raw/pages.jsonl")
    parser.add_argument("--incoming", required=True)
    parser.add_argument("--output", default="data/raw/pages.jsonl")
    args = parser.parse_args()

    existing = read_jsonl(Path(args.existing))
    incoming = read_jsonl(Path(args.incoming))
    merged = merge_by_url(existing, incoming)
    write_jsonl(Path(args.output), merged)
    print(f"Wrote {len(merged)} merged pages to {args.output}; added {len(merged) - len(existing)} net new pages")


if __name__ == "__main__":
    main()
