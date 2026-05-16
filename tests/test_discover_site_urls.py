from scripts.discover_site_urls import (
    canonicalize_url,
    discover_rows,
    discover_site_urls,
    discover_html_links,
    should_keep_url,
)


def test_canonicalize_url_removes_query_fragment_and_trailing_slash():
    assert canonicalize_url("https://example.com/path/?utm=x#top") == "https://example.com/path"


def test_discover_html_links_keeps_same_site_absolute_links():
    html = '<a href="/about">About</a><a href="https://external.example/">Offsite</a>'

    links = discover_html_links("https://example.com/", html, "https://example.com/")

    assert links == ["https://example.com/about"]


def test_should_keep_url_excludes_admin_and_assets():
    assert should_keep_url(
        "https://example.com/about",
        "https://example.com/",
        ["/"],
        ["/wp-admin"],
    )
    assert not should_keep_url(
        "https://example.com/wp-admin",
        "https://example.com/",
        ["/"],
        ["/wp-admin"],
    )
    assert not should_keep_url(
        "https://example.com/image.png",
        "https://example.com/",
        ["/"],
        [],
    )


def test_discover_site_urls_does_not_expand_sitemap_pages(monkeypatch):
    def fake_discover_sitemap_urls(seed_url, timeout, max_sitemaps=10, max_urls=200):
        return ["https://example.com/service"]

    fetched = []

    def fake_fetch_text(url, timeout):
        fetched.append(url)
        if url == "https://example.com/":
            return '<a href="/about">About</a>'
        if url == "https://example.com/service":
            return '<a href="/deep-page">Deep page</a>'
        return ""

    monkeypatch.setattr("scripts.discover_site_urls.discover_sitemap_urls", fake_discover_sitemap_urls)
    monkeypatch.setattr("scripts.discover_site_urls.fetch_text", fake_fetch_text)

    rows = discover_site_urls(
        {
            "brand": "Example",
            "source_type": "competitor_site",
            "seed_urls": ["https://example.com/"],
            "max_pages": 4,
            "max_depth": 2,
        },
        "competitors",
    )

    assert [row["url"] for row in rows] == [
        "https://example.com",
        "https://example.com/service",
        "https://example.com/about",
    ]
    assert "https://example.com/service" not in fetched


def test_discover_rows_supports_own_site_site_mode(monkeypatch):
    def fake_discover_site_urls(source, source_group):
        return [
            {
                "url": "https://own.example",
                "brand": source["brand"],
                "source_type": source["source_type"],
                "source_group": source_group,
                "seed_url": "https://own.example/",
                "discovery_method": "manual_seed",
                "depth": "0",
                "status": "discovered",
            }
        ]

    monkeypatch.setattr("scripts.discover_site_urls.discover_site_urls", fake_discover_site_urls)

    rows = discover_rows(
        {
            "own_site": {
                "brand": "Own",
                "source_type": "official_site",
                "crawl_mode": "site",
                "seed_urls": ["https://own.example/"],
            },
            "competitors": [],
            "industry_sources": [],
        }
    )

    assert rows[0]["source_group"] == "own_site"
    assert rows[0]["brand"] == "Own"
