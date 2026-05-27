from scripts.filter_new_urls import filter_new_rows


def test_filter_new_rows_skips_urls_already_in_pages():
    rows = [
        {"url": "https://example.com/", "brand": "Example"},
        {"url": "https://new.example/", "brand": "New"},
    ]
    pages = [{"url": "https://example.com/"}]

    filtered = filter_new_rows(rows, pages)

    assert filtered == [{"url": "https://new.example/", "brand": "New"}]


def test_filter_new_rows_can_limit_to_source_group():
    rows = [
        {"url": "https://competitor.example/", "source_group": "competitors"},
        {"url": "https://industry.example/", "source_group": "industry_sources"},
    ]

    filtered = filter_new_rows(rows, [], source_group="industry_sources")

    assert filtered == [{"url": "https://industry.example/", "source_group": "industry_sources"}]
