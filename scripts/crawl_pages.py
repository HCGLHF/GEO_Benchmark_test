from __future__ import annotations

import argparse
import csv
import copy
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import (
    FetchAttemptRecord,
    RawPageRecord,
    append_jsonl,
    utc_now_iso,
    write_jsonl,
)
from scripts.paid_fetch_fallback import fetch_with_paid_provider
from scripts.score_content_quality import score_content


DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_inventory(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def apply_cli_overrides(config: dict[str, Any], disable_paid_fallback: bool = False) -> dict[str, Any]:
    overridden = copy.deepcopy(config)
    if disable_paid_fallback:
        paid_fallback = dict(overridden.get("paid_fallback") or {})
        paid_fallback["enabled"] = False
        overridden["paid_fallback"] = paid_fallback
    return overridden


def fallback_html_to_text(html: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def extract_markdown(html: str) -> str:
    try:
        import trafilatura
    except ImportError:
        return fallback_html_to_text(html)
    extracted = trafilatura.extract(html, output_format="markdown")
    return extracted or fallback_html_to_text(html)


def mojibake_score(text: str) -> int:
    markers = ("Ã", "Â", "â€™", "â€œ", "â€", "�")
    return sum(text.count(marker) for marker in markers)


def decode_response_text(response: Any) -> str:
    raw = response.content
    declared_encoding = getattr(response, "encoding", None)
    utf8_text: str | None = None
    try:
        utf8_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if declared_encoding:
        declared_text = raw.decode(declared_encoding, errors="replace")
        if utf8_text is not None and mojibake_score(utf8_text) <= mojibake_score(declared_text):
            return utf8_text
        return declared_text

    if utf8_text is not None:
        return utf8_text
    return raw.decode("utf-8", errors="replace")


def fetch_httpx(url: str, timeout: float) -> tuple[str, str, int | None, str | None]:
    try:
        import httpx

        response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=DEFAULT_HTTP_HEADERS)
        return str(response.url), decode_response_text(response), response.status_code, None
    except Exception as exc:  # network boundary: preserve error and continue run
        return url, "", None, str(exc)


def fetch_playwright(url: str, timeout_ms: int) -> tuple[str, str, int | None, str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return url, "", None, "playwright is not installed"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=DEFAULT_HTTP_HEADERS["User-Agent"],
                extra_http_headers={
                    "Accept-Language": DEFAULT_HTTP_HEADERS["Accept-Language"],
                },
                ignore_https_errors=True,
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            html = page.content()
            final_url = page.url
            status_code = response.status if response else None
            browser.close()
            return final_url, html, status_code, None
    except Exception as exc:
        return url, "", None, str(exc)


def build_raw_page(
    url: str, final_url: str, html: str, status_code: int | None, method: str
) -> RawPageRecord:
    markdown = extract_markdown(html)
    score, error_type = score_content(None, html, markdown, status_code)
    return RawPageRecord(
        url=url,
        final_url=final_url,
        status_code=status_code,
        fetch_method=method,
        html=html,
        markdown=markdown,
        content_quality_score=score,
        error_type=error_type,
        error_message=None,
        collected_at=utc_now_iso(),
    )


def crawl_url(url: str, config: dict[str, Any]) -> tuple[RawPageRecord | None, list[FetchAttemptRecord]]:
    attempts: list[FetchAttemptRecord] = []
    thresholds = config.get("quality_thresholds", {})
    partial_threshold = float(thresholds.get("partial", 0.4))
    timeouts = config.get("timeouts", {})

    final_url, html, status_code, error = fetch_httpx(
        url, float(timeouts.get("httpx_seconds", 20))
    )
    page = build_raw_page(url, final_url, html, status_code, "httpx") if not error else None
    attempts.append(
        FetchAttemptRecord(
            url=url,
            fetch_method="httpx",
            status_code=status_code,
            content_quality_score=page.content_quality_score if page else None,
            error_type=page.error_type if page else "unknown",
            error_message=error,
            attempted_at=utc_now_iso(),
        )
    )
    if page and page.content_quality_score >= partial_threshold:
        return page, attempts

    final_url, html, status_code, error = fetch_playwright(
        url, int(timeouts.get("playwright_seconds", 45)) * 1000
    )
    page = (
        build_raw_page(url, final_url, html, status_code, "playwright")
        if not error
        else None
    )
    attempts.append(
        FetchAttemptRecord(
            url=url,
            fetch_method="playwright",
            status_code=status_code,
            content_quality_score=page.content_quality_score if page else None,
            error_type=page.error_type if page else "unknown",
            error_message=error,
            attempted_at=utc_now_iso(),
        )
    )
    if page and page.content_quality_score >= partial_threshold:
        return page, attempts

    paid_config = config.get("paid_fallback", {})
    if paid_config.get("enabled", False):
        provider = paid_config.get("default_provider", "firecrawl")
        result = fetch_with_paid_provider(url, provider, config)
        score, error_type = score_content(None, result.html, result.markdown, result.status_code)
        attempts.append(
            FetchAttemptRecord(
                url=url,
                fetch_method=provider,
                status_code=result.status_code,
                content_quality_score=score,
                error_type=result.error_type or error_type,
                error_message=result.error_message,
                attempted_at=utc_now_iso(),
            )
        )
        if score >= partial_threshold:
            return (
                RawPageRecord(
                    url=url,
                    final_url=url,
                    status_code=result.status_code,
                    fetch_method=provider,
                    html=result.html,
                    markdown=result.markdown,
                    content_quality_score=score,
                    error_type=error_type,
                    error_message=result.error_message,
                    collected_at=utc_now_iso(),
                ),
                attempts,
            )

    return None, attempts


def select_log_attempt(attempts: list[FetchAttemptRecord]) -> FetchAttemptRecord:
    for attempt in reversed(attempts):
        if attempt.error_message != "playwright is not installed":
            return attempt
    return attempts[-1]


def build_log_row(
    url: str, page: RawPageRecord | None, attempts: list[FetchAttemptRecord]
) -> dict[str, str]:
    attempt = attempts[-1] if page else select_log_attempt(attempts)
    return {
        "url": url,
        "status": "success" if page else "failed",
        "fetch_method": attempt.fetch_method,
        "status_code": "" if attempt.status_code is None else str(attempt.status_code),
        "content_quality_score": ""
        if attempt.content_quality_score is None
        else str(attempt.content_quality_score),
        "error_type": attempt.error_type or "",
        "error_message": attempt.error_message or "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl pages with tiered fetch methods.")
    parser.add_argument("--url-inventory", default="data/raw/url_inventory.csv")
    parser.add_argument("--crawler-config", default="config/crawler.yaml")
    parser.add_argument("--pages-output", default="data/raw/pages.jsonl")
    parser.add_argument("--attempts-output", default="data/raw/fetch_attempts.jsonl")
    parser.add_argument("--logs-output", default="data/raw/crawl_logs.csv")
    parser.add_argument(
        "--disable-paid-fallback",
        action="store_true",
        help="Skip paid crawler APIs for this run and leave failed URLs as paid fallback candidates.",
    )
    args = parser.parse_args()

    with Path(args.crawler_config).open("r", encoding="utf-8") as handle:
        config = apply_cli_overrides(yaml.safe_load(handle) or {}, args.disable_paid_fallback)

    rows = load_inventory(Path(args.url_inventory))
    pages: list[RawPageRecord] = []
    log_rows: list[dict[str, str]] = []
    Path(args.attempts_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.attempts_output).write_text("", encoding="utf-8")

    for row in rows:
        page, attempts = crawl_url(row["url"], config)
        append_jsonl(Path(args.attempts_output), attempts)
        if page:
            pages.append(page)
        log_rows.append(build_log_row(row["url"], page, attempts))

    write_jsonl(Path(args.pages_output), pages)
    Path(args.logs_output).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.logs_output).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(log_rows[0].keys()) if log_rows else ["url"])
        writer.writeheader()
        writer.writerows(log_rows)
    print(f"Crawled {len(pages)} successful pages from {len(rows)} URLs")


if __name__ == "__main__":
    main()
