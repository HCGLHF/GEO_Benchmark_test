from scripts.compare_brands import KEYWORDS, compute_brand_stats, keyword_coverage


def test_compute_brand_stats_counts_pages_chars_and_keywords():
    documents = [
        {
            "brand": "Alpha",
            "url": "https://alpha.example/",
            "content": "AI search visibility with llms.txt and citations.",
        },
        {
            "brand": "Alpha",
            "url": "https://alpha.example/faq",
            "content": "FAQ for generative engine optimization.",
        },
        {
            "brand": "Other",
            "url": "https://other.example/",
            "content": "Answer engine optimization.",
        },
    ]

    stats = compute_brand_stats(documents)

    assert stats["Alpha"]["pages"] == 2
    assert stats["Alpha"]["total_chars"] == len(documents[0]["content"]) + len(documents[1]["content"])
    assert stats["Alpha"]["keyword_counts"]["ai search"] == 1
    assert stats["Alpha"]["keyword_counts"]["llms.txt"] == 1


def test_keyword_coverage_is_fraction_of_keywords_present():
    counts = {keyword: 0 for keyword in KEYWORDS}
    counts["ai search"] = 2
    counts["llms.txt"] = 1

    assert keyword_coverage(counts) == 2 / len(KEYWORDS)
