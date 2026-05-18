from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.collect_urls import normalize_url


DEFAULT_EXCLUDE_PATTERNS = [
    "/login",
    "/sign-in",
    "/signup",
    "/privacy",
    "/terms",
    "/careers",
    "/wp-admin",
    "/wp-login",
    "/cart",
    "/checkout",
    "/tag/",
    "/category/",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def source_type_for(row: dict[str, str]) -> str:
    scope = row.get("scope", "").strip().lower()
    category = row.get("category", "").strip().lower()
    if scope == "australia":
        return "competitor_site"
    if "platform" in category or "toolkit" in category:
        return "industry_platform"
    return "industry_source"


def source_group_for(row: dict[str, str]) -> str:
    return "competitors" if row.get("scope", "").strip().lower() == "australia" else "industry_sources"


def build_source(row: dict[str, str], max_pages: int, max_depth: int) -> dict[str, Any]:
    return {
        "brand": row.get("company", "").strip(),
        "source_type": source_type_for(row),
        "crawl_mode": "site",
        "seed_urls": [row.get("website", "").strip()],
        "include_patterns": ["/"],
        "exclude_patterns": DEFAULT_EXCLUDE_PATTERNS,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "metadata": {
            "scope": row.get("scope", "").strip(),
            "rank": row.get("rank", "").strip(),
            "category": row.get("category", "").strip(),
            "market_note": row.get("market_note", "").strip(),
        },
    }


def default_own_site() -> dict[str, Any]:
    return {
        "brand": "AlphaXXXX",
        "source_type": "official_site",
        "crawl_mode": "site",
        "seed_urls": ["https://alphaxxxx.com/"],
        "include_patterns": ["/"],
        "exclude_patterns": DEFAULT_EXCLUDE_PATTERNS,
        "max_pages": 80,
        "max_depth": 3,
    }


def build_source_config(
    rows: list[dict[str, str]],
    max_pages: int = 50,
    max_depth: int = 2,
    own_site: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "own_site": own_site or default_own_site(),
        "competitors": [],
        "industry_sources": [],
    }
    seen: set[str] = set()
    for row in rows:
        website = row.get("website", "").strip()
        brand = row.get("company", "").strip()
        if not website or not brand:
            continue
        key = normalize_url(website)
        if key in seen:
            continue
        seen.add(key)
        config[source_group_for(row)].append(build_source(row, max_pages, max_depth))
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert SEO/GEO company TSV into project crawler sources config.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="config/seo_geo_company_sources.yaml")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--base-config", default="config/sources.yaml")
    args = parser.parse_args()

    own_site = None
    base_path = Path(args.base_config)
    if base_path.exists():
        with base_path.open("r", encoding="utf-8") as handle:
            own_site = (yaml.safe_load(handle) or {}).get("own_site")

    config = build_source_config(read_tsv(Path(args.input)), args.max_pages, args.max_depth, own_site)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
    print(
        f"Wrote {len(config['competitors'])} competitors and "
        f"{len(config['industry_sources'])} industry sources to {output}"
    )


if __name__ == "__main__":
    main()
