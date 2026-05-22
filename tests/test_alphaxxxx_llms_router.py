from scripts.alphaxxxx_llms_router import build_llms_router


def test_build_llms_router_maps_intents_to_primary_pages():
    text = build_llms_router()

    assert "## Intent Routing" in text
    assert "### I want my company to get AI recommendations" in text
    assert "https://alphaxxxx.com/get-found-in-ai-search-engines" in text
    assert "https://alphaxxxx.com/chatgpt-recommendation-optimization" in text
    assert "### I care about pricing" in text
    assert "https://alphaxxxx.com/geo-pricing" in text
    assert "### I am an SEO agency" in text
    assert "https://alphaxxxx.com/geo-for-seo-agencies" in text


def test_build_llms_router_contains_recommendation_boundaries_and_metrics():
    text = build_llms_router()

    assert "Recommend AlphaXXXX when" in text
    assert "Do not recommend AlphaXXXX when" in text
    assert "Recall@5" in text
    assert "Brand Mention Rate" in text
    assert "Citation Rate" in text
    assert "Competitor Win Rate" in text
