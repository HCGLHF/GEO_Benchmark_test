from scripts.import_seo_geo_sources import build_source_config


def test_build_source_config_groups_australia_as_competitors_and_global_as_industry():
    rows = [
        {
            "scope": "Australia",
            "rank": "1",
            "company": "Local GEO",
            "website": "https://local.example/",
            "category": "GEO agency",
            "market_note": "Australia",
        },
        {
            "scope": "Global",
            "rank": "1",
            "company": "Global Platform",
            "website": "https://global.example/",
            "category": "GEO AI visibility platform",
            "market_note": "Global",
        },
    ]

    config = build_source_config(rows, max_pages=25, max_depth=3)

    assert config["competitors"][0]["brand"] == "Local GEO"
    assert config["competitors"][0]["source_type"] == "competitor_site"
    assert config["competitors"][0]["crawl_mode"] == "site"
    assert config["competitors"][0]["seed_urls"] == ["https://local.example/"]
    assert config["competitors"][0]["max_pages"] == 25
    assert config["competitors"][0]["max_depth"] == 3
    assert config["industry_sources"][0]["brand"] == "Global Platform"
    assert config["industry_sources"][0]["source_type"] == "industry_platform"


def test_build_source_config_deduplicates_by_normalized_website():
    rows = [
        {
            "scope": "Global",
            "rank": "1",
            "company": "First",
            "website": "https://example.com/",
            "category": "SEO agency",
            "market_note": "Global",
        },
        {
            "scope": "Global",
            "rank": "2",
            "company": "Second",
            "website": "https://example.com",
            "category": "SEO agency",
            "market_note": "Global",
        },
    ]

    config = build_source_config(rows)

    assert [source["brand"] for source in config["industry_sources"]] == ["First"]
