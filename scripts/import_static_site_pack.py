from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import utc_now_iso
from scripts.crawl_pages import extract_markdown


INVENTORY_FIELDS = [
    "url",
    "brand",
    "source_type",
    "source_group",
    "seed_url",
    "discovery_method",
    "depth",
    "status",
]


def normalized_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def base_path(base_url: str) -> str:
    path = urlparse(normalized_base_url(base_url)).path
    return path if path.endswith("/") else path + "/"


def rewrite_root_links(html: str, base_url: str) -> str:
    prefix = base_path(base_url)
    return re.sub(r"""(?P<attr>\b(?:href|src)=["'])/""", rf"\g<attr>{prefix}", html)


def importable_paths(site_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in site_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(site_dir).as_posix()
        if relative == "llms.txt" or path.name == "index.html":
            paths.append(path)

    def sort_key(path: Path) -> tuple[int, str]:
        relative = path.relative_to(site_dir).as_posix()
        if relative == "index.html":
            return (0, relative)
        if relative == "llms.txt":
            return (1, relative)
        return (2, relative)

    return sorted(paths, key=sort_key)


def canonical_url_for_path(path: Path, *, site_dir: Path, base_url: str) -> str:
    base = normalized_base_url(base_url)
    relative = path.relative_to(site_dir)
    if path.name == "index.html":
        parent = relative.parent.as_posix()
        return base if parent == "." else f"{base}{parent.strip('/')}/"
    return f"{base}{relative.as_posix()}"


def markdown_for_path(path: Path, text: str, base_url: str) -> tuple[str, str]:
    if path.suffix.lower() == ".html":
        html = rewrite_root_links(text, base_url)
        markdown = extract_markdown(html)
        return html, markdown
    return "", text.strip()


def import_static_site_pack(
    *,
    site_dir: Path,
    base_url: str,
    brand: str,
    raw_pages_path: Path,
    inventory_path: Path,
) -> dict[str, int | str]:
    if not site_dir.exists():
        raise FileNotFoundError(f"Static site directory not found: {site_dir}")

    pages: list[dict[str, object]] = []
    inventory_rows: list[dict[str, str]] = []
    seed_url = normalized_base_url(base_url)
    collected_at = utc_now_iso()
    for path in importable_paths(site_dir):
        text = path.read_text(encoding="utf-8")
        html, markdown = markdown_for_path(path, text, base_url)
        url = canonical_url_for_path(path, site_dir=site_dir, base_url=base_url)
        if not markdown.strip():
            continue
        pages.append(
            {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "fetch_method": "static_pack",
                "html": html,
                "markdown": markdown.strip(),
                "content_quality_score": 1.0,
                "error_type": None,
                "error_message": None,
                "collected_at": collected_at,
            }
        )
        inventory_rows.append(
            {
                "url": url,
                "brand": brand,
                "source_type": "owned_site",
                "source_group": "own_site",
                "seed_url": seed_url,
                "discovery_method": "static_pack",
                "depth": "0",
                "status": "discovered",
            }
        )

    raw_pages_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_pages_path.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False) + "\n")

    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(inventory_rows)

    return {
        "site_dir": str(site_dir),
        "base_url": normalized_base_url(base_url),
        "raw_pages": str(raw_pages_path),
        "url_inventory": str(inventory_path),
        "imported_pages": len(pages),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a static site pack into raw GEO benchmark corpus files.")
    parser.add_argument("--site-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--brand", default="AlphaXXXX")
    parser.add_argument("--raw-pages", default="data/raw/alpha_geo_recall_pages.jsonl")
    parser.add_argument("--url-inventory", default="data/raw/alpha_geo_recall_urls.csv")
    args = parser.parse_args()
    result = import_static_site_pack(
        site_dir=Path(args.site_dir),
        base_url=args.base_url,
        brand=args.brand,
        raw_pages_path=Path(args.raw_pages),
        inventory_path=Path(args.url_inventory),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
