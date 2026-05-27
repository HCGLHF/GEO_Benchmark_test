from scripts.collect_urls import collect_url_rows


def test_collect_url_rows_flattens_sources_and_removes_duplicates():
    config = {
        "own_site": {
            "brand": "Own",
            "source_type": "official_site",
            "urls": ["https://example.com/", "https://example.com/#top"],
        },
        "competitors": [
            {
                "brand": "Competitor",
                "source_type": "competitor_site",
                "urls": ["https://competitor.example/product"],
            }
        ],
        "industry_sources": [
            {
                "brand": "Media",
                "source_type": "review_site",
                "urls": ["https://media.example/best-tools"],
            }
        ],
    }

    rows = collect_url_rows(config)

    assert len(rows) == 3
    assert rows[0] == {
        "url": "https://example.com",
        "brand": "Own",
        "source_type": "official_site",
        "source_group": "own_site",
    }
    assert rows[1]["brand"] == "Competitor"
    assert rows[2]["source_type"] == "review_site"
