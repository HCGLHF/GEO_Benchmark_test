from scripts._common import FetchAttemptRecord
from scripts.crawl_pages import apply_cli_overrides, build_log_row, fallback_html_to_text


def test_fallback_html_to_text_removes_nextjs_script_state():
    html = (
        "<html><main>ALPHAXXXX helps AI search visibility.</main>"
        '<script>{"forbidden":"$undefined","unauthorized":"$undefined"}</script></html>'
    )

    text = fallback_html_to_text(html)

    assert "ALPHAXXXX helps AI search visibility." in text
    assert "forbidden" not in text
    assert "unauthorized" not in text


def test_apply_cli_overrides_can_disable_paid_fallback():
    config = {"paid_fallback": {"enabled": True, "default_provider": "firecrawl"}}

    overridden = apply_cli_overrides(config, disable_paid_fallback=True)

    assert overridden["paid_fallback"]["enabled"] is False
    assert config["paid_fallback"]["enabled"] is True


def test_build_log_row_keeps_httpx_failure_when_playwright_is_unavailable():
    attempts = [
        FetchAttemptRecord(
            url="https://example.com/",
            fetch_method="httpx",
            status_code=403,
            content_quality_score=0.2,
            error_type="captcha",
            error_message=None,
            attempted_at="2026-05-15T00:00:00Z",
        ),
        FetchAttemptRecord(
            url="https://example.com/",
            fetch_method="playwright",
            status_code=None,
            content_quality_score=None,
            error_type="unknown",
            error_message="playwright is not installed",
            attempted_at="2026-05-15T00:00:01Z",
        ),
    ]

    row = build_log_row("https://example.com/", None, attempts)

    assert row["status"] == "failed"
    assert row["fetch_method"] == "httpx"
    assert row["status_code"] == "403"
    assert row["content_quality_score"] == "0.2"
    assert row["error_type"] == "captcha"
