from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import append_jsonl
from scripts.crawl_pages import (
    apply_cli_overrides,
    build_log_row,
    crawl_url,
    load_inventory,
)


def write_logs(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "url",
        "status",
        "fetch_method",
        "status_code",
        "content_quality_score",
        "error_type",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def crawl_one(index: int, row: dict[str, str], config: dict[str, Any]) -> tuple[int, dict[str, str], bool, Any, list[Any]]:
    page, attempts = crawl_url(row["url"], config)
    return index, row, page is not None, page, attempts


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl pages concurrently using the existing tiered crawler.")
    parser.add_argument("--url-inventory", default="data/raw/url_inventory.csv")
    parser.add_argument("--crawler-config", default="config/crawler.yaml")
    parser.add_argument("--pages-output", default="data/raw/pages.jsonl")
    parser.add_argument("--attempts-output", default="data/raw/fetch_attempts.jsonl")
    parser.add_argument("--logs-output", default="data/raw/crawl_logs.csv")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--disable-paid-fallback",
        action="store_true",
        help="Skip paid crawler APIs for this run and leave failed URLs as paid fallback candidates.",
    )
    args = parser.parse_args()

    with Path(args.crawler_config).open("r", encoding="utf-8") as handle:
        config = apply_cli_overrides(yaml.safe_load(handle) or {}, args.disable_paid_fallback)

    rows = load_inventory(Path(args.url_inventory))
    pages_path = Path(args.pages_output)
    attempts_path = Path(args.attempts_output)
    logs_path = Path(args.logs_output)
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.write_text("", encoding="utf-8")
    attempts_path.write_text("", encoding="utf-8")

    log_rows_by_index: dict[int, dict[str, str]] = {}
    success_count = 0
    completed = 0
    total = len(rows)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(crawl_one, index, row, config) for index, row in enumerate(rows)]
        for future in as_completed(futures):
            index, row, ok, page, attempts = future.result()
            completed += 1
            if ok:
                success_count += 1
                append_jsonl(pages_path, [page])
            append_jsonl(attempts_path, attempts)
            log_rows_by_index[index] = build_log_row(row["url"], page, attempts)
            if completed == total or completed % 10 == 0:
                print(f"Progress: {completed}/{total} crawled, {success_count} successful", flush=True)

    log_rows = [log_rows_by_index[index] for index in range(total) if index in log_rows_by_index]
    write_logs(logs_path, log_rows)
    print(f"Crawled {success_count} successful pages from {total} URLs")


if __name__ == "__main__":
    main()
