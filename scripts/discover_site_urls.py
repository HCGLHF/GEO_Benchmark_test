from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.collect_urls import collect_url_rows, normalize_url


SKIP_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
    ".zip",
    ".css",
    ".js",
    ".ico",
    ".xml",
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(value)


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    parsed = parsed._replace(fragment="", query="")
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    parsed = parsed._replace(path=path)
    return urlunparse(parsed)


def same_site(url: str, seed: str) -> bool:
    return urlparse(url).netloc.lower().removeprefix("www.") == urlparse(seed).netloc.lower().removeprefix("www.")


def should_keep_url(url: str, seed: str, include_patterns: list[str], exclude_patterns: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not same_site(url, seed):
        return False
    lower_path = parsed.path.lower()
    if any(lower_path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if any(pattern and pattern in parsed.path for pattern in exclude_patterns):
        return False
    return not include_patterns or any(pattern in parsed.path for pattern in include_patterns)


def fetch_text(url: str, timeout: float) -> str:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=timeout)
        if response.status_code >= 400:
            return ""
        return response.text
    except Exception:
        return ""


def discover_sitemap_urls(seed_url: str, timeout: float, max_sitemaps: int = 10, max_urls: int = 200) -> list[str]:
    parsed = urlparse(seed_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_candidates = [f"{base}/sitemap.xml"]

    robots = fetch_text(f"{base}/robots.txt", timeout)
    for line in robots.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_candidates.append(line.split(":", 1)[1].strip())

    urls: list[str] = []
    seen_sitemaps: set[str] = set()
    queue = deque(sitemap_candidates)
    while queue and len(seen_sitemaps) < max_sitemaps and len(urls) < max_urls:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        body = fetch_text(sitemap_url, timeout)
        if not body.strip():
            continue
        try:
            root = ET.fromstring(body.encode("utf-8"))
        except ET.ParseError:
            continue
        for loc in root.iter():
            if not loc.tag.endswith("loc") or not loc.text:
                continue
            loc_url = loc.text.strip()
            if loc_url.endswith(".xml"):
                queue.append(loc_url)
            else:
                urls.append(canonicalize_url(loc_url))
                if len(urls) >= max_urls:
                    break
    return urls


def discover_html_links(url: str, html: str, seed_url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    links: list[str] = []
    for href in parser.links:
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = canonicalize_url(urljoin(url, href))
        if same_site(absolute, seed_url):
            links.append(absolute)
    return links


def discover_site_urls(source: dict, source_group: str, timeout: float = 8.0) -> list[dict[str, str]]:
    seed_urls = source.get("seed_urls") or source.get("urls") or []
    include_patterns = source.get("include_patterns") or ["/"]
    exclude_patterns = source.get("exclude_patterns") or []
    max_pages = int(source.get("max_pages") or 50)
    max_depth = int(source.get("max_depth") or 2)

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque()

    for seed_url in seed_urls:
        seed = canonicalize_url(seed_url)
        queue.append((seed, 0, "manual_seed"))
        for sitemap_url in discover_sitemap_urls(seed, timeout, max_urls=max_pages * 4):
            queue.append((sitemap_url, 0, "sitemap"))

    while queue and len(rows) < max_pages:
        url, depth, method = queue.popleft()
        if url in seen:
            continue
        seed_url = canonicalize_url(seed_urls[0])
        if not should_keep_url(url, seed_url, include_patterns, exclude_patterns):
            continue
        seen.add(url)
        rows.append(
            {
                "url": normalize_url(url),
                "brand": source.get("brand", ""),
                "source_type": source.get("source_type", ""),
                "source_group": source_group,
                "seed_url": seed_url,
                "discovery_method": method,
                "depth": str(depth),
                "status": "discovered",
            }
        )
        if depth >= max_depth or method == "sitemap":
            continue
        html = fetch_text(url, timeout)
        for link in discover_html_links(url, html, seed_url):
            if link not in seen:
                queue.append((link, depth + 1, "html_link"))

    return rows


def discover_rows(config: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    page_mode_config = {
        "own_site": config.get("own_site", {})
        if config.get("own_site", {}).get("crawl_mode", "page") != "site"
        else {},
        "competitors": [
            source for source in config.get("competitors", []) or [] if source.get("crawl_mode", "page") != "site"
        ],
        "industry_sources": [
            source for source in config.get("industry_sources", []) or [] if source.get("crawl_mode", "page") != "site"
        ],
    }
    for row in collect_url_rows(page_mode_config):
        key = row["url"]
        if key not in seen:
            seen.add(key)
            rows.append(
                row
                | {
                    "seed_url": row["url"],
                    "discovery_method": "manual_seed",
                    "depth": "0",
                    "status": "discovered",
                }
            )

    for group_name in ("competitors", "industry_sources"):
        for source in config.get(group_name, []) or []:
            if source.get("crawl_mode", "page") == "site":
                for row in discover_site_urls(source, group_name):
                    key = row["url"]
                    if key not in seen:
                        seen.add(key)
                        rows.append(row)

    own_site = config.get("own_site") or {}
    if own_site.get("crawl_mode", "page") == "site":
        for row in discover_site_urls(own_site, "own_site"):
            key = row["url"]
            if key not in seen:
                seen.add(key)
                rows.append(row)

    return rows


def write_discovered_urls(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "url",
        "brand",
        "source_type",
        "source_group",
        "seed_url",
        "discovery_method",
        "depth",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover site URLs from seeds, sitemaps, and internal links.")
    parser.add_argument("--config", default="config/sources.yaml")
    parser.add_argument("--output", default="data/raw/discovered_urls.csv")
    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    rows = discover_rows(config)
    write_discovered_urls(Path(args.output), rows)
    print(f"Wrote {len(rows)} discovered URLs to {args.output}")


if __name__ == "__main__":
    main()
