from __future__ import annotations

import argparse
import csv
from pathlib import Path
from urllib.parse import urldefrag

import yaml


def normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    if clean.endswith("/") and clean.count("/") > 2:
        clean = clean.rstrip("/")
    return clean


def collect_url_rows(config: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    own_site = config.get("own_site") or {}
    for url in own_site.get("urls", []) or []:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen.add(normalized)
            rows.append(
                {
                    "url": normalized,
                    "brand": own_site.get("brand", ""),
                    "source_type": own_site.get("source_type", "official_site"),
                    "source_group": "own_site",
                }
            )

    for group_name in ("competitors", "industry_sources"):
        for source in config.get(group_name, []) or []:
            for url in source.get("urls", []) or []:
                normalized = normalize_url(url)
                if normalized in seen:
                    continue
                seen.add(normalized)
                rows.append(
                    {
                        "url": normalized,
                        "brand": source.get("brand", ""),
                        "source_type": source.get("source_type", ""),
                        "source_group": group_name,
                    }
                )

    return rows


def write_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["url", "brand", "source_type", "source_group"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect configured GEO source URLs.")
    parser.add_argument("--config", default="config/sources.yaml")
    parser.add_argument("--output", default="data/raw/url_inventory.csv")
    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    rows = collect_url_rows(config)
    write_inventory(Path(args.output), rows)
    print(f"Wrote {len(rows)} URLs to {args.output}")


if __name__ == "__main__":
    main()
