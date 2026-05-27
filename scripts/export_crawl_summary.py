from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import FetchAttemptRecord
from scripts.crawl_pages import build_log_row


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_page_urls(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        return {json.loads(line)["url"] for line in handle if line.strip()}


def read_attempts_by_url(path: Path) -> dict[str, list[FetchAttemptRecord]]:
    attempts_by_url: dict[str, list[FetchAttemptRecord]] = collections.defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            attempt = FetchAttemptRecord(**json.loads(line))
            attempts_by_url[attempt.url].append(attempt)
    return attempts_by_url


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export crawl logs and paid fallback candidates from attempts.")
    parser.add_argument("--url-inventory", default="data/raw/discovered_urls.csv")
    parser.add_argument("--pages", default="data/raw/pages.jsonl")
    parser.add_argument("--attempts", default="data/raw/fetch_attempts.jsonl")
    parser.add_argument("--logs-output", default="data/raw/crawl_logs.csv")
    parser.add_argument("--candidates-output", default="data/raw/paid_fallback_candidates.csv")
    args = parser.parse_args()

    inventory = read_csv(Path(args.url_inventory))
    brand_by_url = {row["url"]: row.get("brand", "") for row in inventory}
    page_urls = read_page_urls(Path(args.pages))
    attempts_by_url = read_attempts_by_url(Path(args.attempts))

    logs: list[dict[str, str]] = []
    candidates: list[dict[str, str]] = []
    for row in inventory:
        url = row["url"]
        attempts = attempts_by_url.get(url, [])
        if not attempts:
            continue
        log_row = build_log_row(url, object() if url in page_urls else None, attempts)
        logs.append(log_row)
        if log_row["status"] == "failed":
            candidates.append(
                {
                    "url": url,
                    "brand": brand_by_url.get(url, ""),
                    "error_type": log_row["error_type"],
                    "status_code": log_row["status_code"],
                    "content_quality_score": log_row["content_quality_score"],
                }
            )

    write_csv(
        Path(args.logs_output),
        logs,
        ["url", "status", "fetch_method", "status_code", "content_quality_score", "error_type", "error_message"],
    )
    write_csv(
        Path(args.candidates_output),
        candidates,
        ["url", "brand", "error_type", "status_code", "content_quality_score"],
    )
    print(f"Wrote {len(logs)} crawl log rows and {len(candidates)} paid fallback candidates")


if __name__ == "__main__":
    main()
