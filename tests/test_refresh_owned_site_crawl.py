from pathlib import Path

from scripts.refresh_owned_site_crawl import build_owned_site_source, build_parallel_crawl_command


def test_build_owned_site_source_uses_multiple_seed_urls() -> None:
    source = build_owned_site_source(
        brand="AlphaXXXX",
        seed_urls=["https://alphaxxxx.com/", "https://docs.alphaxxxx.com/"],
        max_pages=75,
        max_depth=3,
    )

    assert source["brand"] == "AlphaXXXX"
    assert source["crawl_mode"] == "site"
    assert source["seed_urls"] == ["https://alphaxxxx.com/", "https://docs.alphaxxxx.com/"]
    assert source["max_pages"] == 75
    assert source["max_depth"] == 3


def test_build_parallel_crawl_command_uses_current_cli_flags() -> None:
    command = build_parallel_crawl_command(
        discovered_output=Path("data/raw/alpha_update_discovered_urls.csv"),
        pages_output=Path("data/raw/alpha_update_pages.jsonl"),
        attempts_output=Path("data/raw/alpha_update_fetch_attempts.jsonl"),
        logs_output=Path("data/raw/alpha_update_crawl_logs.csv"),
        crawler_config=Path("config/crawler.yaml"),
        workers=4,
        disable_paid_fallback=True,
    )

    joined = " ".join(command).replace("\\", "/")
    assert "scripts.crawl_pages_parallel" in joined
    assert "--url-inventory data/raw/alpha_update_discovered_urls.csv" in joined
    assert "--pages-output data/raw/alpha_update_pages.jsonl" in joined
    assert "--attempts-output data/raw/alpha_update_fetch_attempts.jsonl" in joined
    assert "--logs-output data/raw/alpha_update_crawl_logs.csv" in joined
    assert "--disable-paid-fallback" in command
