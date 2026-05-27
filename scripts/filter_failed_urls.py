from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def filter_failed_rows(inventory_rows: list[dict[str, str]], log_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    failed_urls = {row.get("url", "") for row in log_rows if row.get("status") == "failed"}
    return [row for row in inventory_rows if row.get("url", "") in failed_urls]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter an inventory to rows that failed in a crawl log.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--logs", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inventory_rows = read_csv(Path(args.inventory))
    log_rows = read_csv(Path(args.logs))
    failed_rows = filter_failed_rows(inventory_rows, log_rows)
    fields = list(inventory_rows[0].keys()) if inventory_rows else ["url"]
    write_csv(Path(args.output), failed_rows, fields)
    print(f"Wrote {len(failed_rows)} failed URLs to {args.output}")


if __name__ == "__main__":
    main()
