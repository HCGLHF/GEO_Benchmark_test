from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discover_site_urls import discover_site_urls, write_discovered_urls


def build_owned_site_source(
    *,
    brand: str,
    seed_urls: list[str],
    max_pages: int,
    max_depth: int,
) -> dict:
    return {
        "brand": brand,
        "source_type": "owned_site",
        "crawl_mode": "site",
        "seed_urls": seed_urls,
        "include_patterns": ["/"],
        "exclude_patterns": [],
        "max_pages": max_pages,
        "max_depth": max_depth,
    }


def build_parallel_crawl_command(
    *,
    discovered_output: Path,
    pages_output: Path,
    attempts_output: Path,
    logs_output: Path,
    crawler_config: Path,
    workers: int,
    disable_paid_fallback: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "scripts.crawl_pages_parallel",
        "--url-inventory",
        str(discovered_output),
        "--crawler-config",
        str(crawler_config),
        "--pages-output",
        str(pages_output),
        "--attempts-output",
        str(attempts_output),
        "--logs-output",
        str(logs_output),
        "--workers",
        str(workers),
    ]
    if disable_paid_fallback:
        command.append("--disable-paid-fallback")
    return command


def refresh_owned_site_crawl(
    *,
    brand: str,
    seed_urls: list[str],
    discovered_output: Path,
    pages_output: Path,
    attempts_output: Path,
    logs_output: Path,
    crawler_config: Path,
    workers: int,
    max_pages: int,
    max_depth: int,
    disable_paid_fallback: bool,
) -> int:
    if not seed_urls:
        raise ValueError("At least one --seed-url is required.")
    source = build_owned_site_source(brand=brand, seed_urls=seed_urls, max_pages=max_pages, max_depth=max_depth)
    print(f"Discovering {brand} URLs from {len(seed_urls)} seed URL(s)...", flush=True)
    rows = discover_site_urls(source, "own_site")
    write_discovered_urls(discovered_output, rows)
    print(f"Discovered {len(rows)} URLs -> {discovered_output}", flush=True)
    if not rows:
        print("No URLs discovered; skipping fetch.", flush=True)
        return 2

    command = build_parallel_crawl_command(
        discovered_output=discovered_output,
        pages_output=pages_output,
        attempts_output=attempts_output,
        logs_output=logs_output,
        crawler_config=crawler_config,
        workers=workers,
        disable_paid_fallback=disable_paid_fallback,
    )
    print("Fetching discovered pages with local crawler...", flush=True)
    result = subprocess.run(command, check=False)
    return int(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and fetch the owned site in one monitored pipeline step.")
    parser.add_argument("--brand", default="AlphaXXXX")
    parser.add_argument("--seed-url", action="append", required=True)
    parser.add_argument("--discovered-output", default="data/raw/alpha_update_discovered_urls.csv")
    parser.add_argument("--pages-output", default="data/raw/alpha_update_pages.jsonl")
    parser.add_argument("--attempts-output", default="data/raw/alpha_update_fetch_attempts.jsonl")
    parser.add_argument("--logs-output", default="data/raw/alpha_update_crawl_logs.csv")
    parser.add_argument("--crawler-config", default="config/crawler.yaml")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-pages", type=int, default=75)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--disable-paid-fallback", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        refresh_owned_site_crawl(
            brand=args.brand,
            seed_urls=[url for url in args.seed_url if url.strip()],
            discovered_output=Path(args.discovered_output),
            pages_output=Path(args.pages_output),
            attempts_output=Path(args.attempts_output),
            logs_output=Path(args.logs_output),
            crawler_config=Path(args.crawler_config),
            workers=args.workers,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            disable_paid_fallback=args.disable_paid_fallback,
        )
    )


if __name__ == "__main__":
    main()
