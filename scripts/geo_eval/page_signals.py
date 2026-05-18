from __future__ import annotations

from typing import Any


def contains_any(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def infer_page_type(url: str, title: str, text: str) -> str:
    haystack = f"{url} {title} {text}".lower()
    if any(term in haystack for term in ["/pricing", "/cost", "/packages", "pricing", "cost", "packages"]):
        return "pricing_page"
    if any(term in haystack for term in ["/case-study", "/results", "case study", "client results"]):
        return "case_study"
    if any(term in haystack for term in ["/audit", "free audit", "assessment", "checker"]):
        return "audit_page"
    if any(term in haystack for term in ["/services", "/geo", "/ai-search", "agency", "consulting", "optimization"]):
        return "service_page"
    if any(term in haystack for term in ["/about", "about us", "team"]):
        return "about_page"
    return "content_page"


def tag_page(row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or "")
    title = str(row.get("title") or "")
    text = str(row.get("markdown") or row.get("text") or "")
    haystack = f"{url} {title} {text}"
    return {
        "url": url,
        "brand": row.get("brand", ""),
        "title": title,
        "page_type": infer_page_type(url, title, text),
        "platform_signals": contains_any(haystack, ["ChatGPT", "Perplexity", "Gemini", "AI Overviews", "Copilot"]),
        "local_signals": contains_any(haystack, ["Australia", "Sydney", "Melbourne", "Brisbane"]),
        "trust_signals": contains_any(haystack, ["case study", "client results", "testimonial", "methodology"]),
        "conversion_signals": contains_any(haystack, ["free audit", "consultation", "quote", "pricing"]),
        "topic_signals": contains_any(haystack, ["GEO", "generative engine optimization", "AI search", "AI SEO", "LLM visibility"]),
    }
