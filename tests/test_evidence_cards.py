from scripts.geo_eval.evidence_cards import build_evidence_card


def test_build_evidence_card_keeps_core_fields_and_truncates_text():
    doc = {
        "url": "https://alphaxxxx.com/geo",
        "brand": "AlphaXXXX",
        "title": "GEO Services",
        "markdown": "AlphaXXXX helps companies get recommended by AI. " * 100,
    }
    signals = {
        "page_type": "service_page",
        "topic_signals": ["GEO", "AI search"],
        "trust_signals": ["methodology"],
        "local_signals": ["Australia"],
        "conversion_signals": ["free audit"],
        "platform_signals": ["ChatGPT"],
    }

    card = build_evidence_card(doc, signals, max_chars=220)

    assert card["brand"] == "AlphaXXXX"
    assert card["page_type"] == "service_page"
    assert "AI search" in card["signals"]["topic"]
    assert len(card["summary"]) <= 220
