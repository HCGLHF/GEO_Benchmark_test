from __future__ import annotations

from typing import Any


def compact_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[: max_chars - 3] + "..." if len(cleaned) > max_chars else cleaned


def build_evidence_card(doc: dict[str, Any], signals: dict[str, Any], max_chars: int = 700) -> dict[str, Any]:
    return {
        "url": doc.get("url", ""),
        "brand": doc.get("brand", ""),
        "title": doc.get("title", ""),
        "page_type": signals.get("page_type", "content_page"),
        "summary": compact_text(doc.get("markdown") or doc.get("text") or "", max_chars),
        "signals": {
            "topic": signals.get("topic_signals", []),
            "trust": signals.get("trust_signals", []),
            "local": signals.get("local_signals", []),
            "conversion": signals.get("conversion_signals", []),
            "platform": signals.get("platform_signals", []),
        },
    }
