from scripts.geo_eval.page_signals import tag_page


def test_tag_page_detects_service_page_and_local_signals():
    row = {
        "url": "https://horntech.com.au/ai-search-optimisation-sydney-2026-cost-guide",
        "title": "AI Search Optimisation Sydney 2026 Cost Guide",
        "markdown": "Get found in AI search engines. Free audit and pricing for Sydney businesses.",
    }
    tags = tag_page(row)

    assert tags["page_type"] == "pricing_page"
    assert "Sydney" in tags["local_signals"]
    assert "free audit" in tags["conversion_signals"]
    assert "pricing" in tags["conversion_signals"]
    assert "AI search" in tags["topic_signals"]


def test_tag_page_defaults_to_content_page():
    row = {"url": "https://example.com/blog/post", "title": "Thoughts", "markdown": "General content"}

    assert tag_page(row)["page_type"] == "content_page"
