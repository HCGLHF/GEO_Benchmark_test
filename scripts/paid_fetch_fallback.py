from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import load_dotenv


class PaidFetchResult(BaseModel):
    provider: str
    status_code: int | None = None
    html: str = ""
    markdown: str = ""
    error_type: str | None = None
    error_message: str | None = None


def fetch_with_paid_provider(
    url: str, provider: str, config: dict[str, Any]
) -> PaidFetchResult:
    load_dotenv()
    paid_config = config.get("paid_fallback", {})
    if not paid_config.get("enabled", False):
        return PaidFetchResult(
            provider=provider,
            error_type="unknown",
            error_message="paid fallback disabled",
        )

    if provider != "firecrawl":
        return PaidFetchResult(
            provider=provider,
            error_type="unknown",
            error_message=f"{provider} adapter is not implemented in MVP",
        )

    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key or "YOUR_FIRECRAWL" in api_key:
        return PaidFetchResult(
            provider=provider,
            error_type="unknown",
            error_message="missing FIRECRAWL_API_KEY in environment or .env",
        )

    try:
        import httpx

        response = httpx.post(
            "https://api.firecrawl.dev/v2/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
                "timeout": 60000,
            },
            timeout=90,
        )
    except Exception as exc:
        return PaidFetchResult(
            provider=provider,
            error_type="unknown",
            error_message=str(exc),
        )

    if response.status_code >= 400:
        return PaidFetchResult(
            provider=provider,
            status_code=response.status_code,
            error_type="http_error",
            error_message=response.text[:500],
        )

    try:
        payload = response.json()
    except ValueError:
        return PaidFetchResult(
            provider=provider,
            status_code=response.status_code,
            error_type="parse_error",
            error_message=response.text[:500],
        )

    if payload.get("success") is False:
        return PaidFetchResult(
            provider=provider,
            status_code=response.status_code,
            error_type="unknown",
            error_message=str(payload.get("error") or payload)[:500],
        )

    data = payload.get("data") or payload
    metadata = data.get("metadata") or {}
    return PaidFetchResult(
        provider=provider,
        status_code=response.status_code,
        html=data.get("html") or data.get("rawHtml") or "",
        markdown=data.get("markdown") or "",
        error_type=None,
        error_message=None if data.get("markdown") or data.get("html") else f"empty Firecrawl response for {metadata.get('sourceURL', url)}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a paid crawler fallback adapter.")
    parser.add_argument("url")
    parser.add_argument("--provider", default="firecrawl")
    parser.add_argument("--crawler-config", default="config/crawler.yaml")
    args = parser.parse_args()
    with Path(args.crawler_config).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    result = fetch_with_paid_provider(args.url, args.provider, config)
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
