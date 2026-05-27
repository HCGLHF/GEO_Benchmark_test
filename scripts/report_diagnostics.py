from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlparse


QUERY_LOSS_FIELDS = [
    "query_id",
    "query",
    "model",
    "persona",
    "journey_stage",
    "target_rank",
    "winning_brand",
    "winning_url",
    "winning_title",
    "loss_reason",
]

COMPETITOR_DISPLACEMENT_FIELDS = [
    "winning_brand",
    "winning_url",
    "winning_title",
    "top5_query_count",
    "models",
    "personas",
    "journey_stages",
    "signals",
]

PAGE_OPTIMIZATION_FIELDS = [
    "priority",
    "url",
    "title",
    "problem",
    "recommended_modules",
    "validation_metric",
]

URL_TOP5_FIELDS = [
    "rank",
    "url",
    "domain",
    "brand",
    "title",
    "source_type",
    "top5_query_count",
    "top5_hit_count",
    "best_rank",
    "avg_rank",
    "models",
    "personas",
    "journey_stages",
    "page_intent",
    "signals",
]

DOMAIN_TOP5_FIELDS = [
    "rank",
    "domain",
    "brand",
    "top5_query_count",
    "top5_hit_count",
    "best_rank",
    "avg_rank",
    "top_urls",
    "models",
    "personas",
    "journey_stages",
    "signals",
]

PERSONA_STAGE_LOSS_FIELDS = [
    "persona",
    "journey_stage",
    "query_count",
    "target_top5_count",
    "target_top5_share",
    "not_ranked_count",
    "leading_winner",
    "winner_count",
    "top_displacing_domain",
    "top_displacing_url",
    "top_displacing_url_count",
    "primary_loss_reasons",
    "recommended_action",
]

PAGE_INTENT_WEAKNESS_FIELDS = [
    "page_intent",
    "page_count",
    "weak_page_count",
    "zero_top5_count",
    "total_top5_queries",
    "strongest_url",
    "weakest_urls",
    "recommended_focus",
]

CONTENT_OPTIMIZATION_ACTION_FIELDS = [
    "priority",
    "url",
    "title",
    "page_intent",
    "target_persona",
    "target_stage",
    "problem",
    "competitor_benchmark_url",
    "competitor_benchmark_brand",
    "content_gaps",
    "internal_links_to_add",
    "faq_questions",
    "schema_recommendation",
    "validation_metric",
]

SIGNAL_LABELS = {
    "sydney": "Sydney",
    "australia": "Australia",
    "pricing": "pricing",
    "cost": "cost",
    "free audit": "free audit",
    "audit": "audit",
    "chatgpt": "ChatGPT",
    "perplexity": "Perplexity",
    "ai overviews": "AI Overviews",
    "get found in ai search engines": "get found in AI search engines",
    "questions before spending": "buyer questions",
    "checklist": "checklist",
    "case study": "case study",
    "marketing teams": "marketing teams",
    "seo agency": "SEO agency",
    "local business": "local business",
    "sme": "SME",
}


def _signals_from_text(*parts: Any, limit: int = 5) -> list[str]:
    text = " ".join(str(part or "") for part in parts).lower()
    signals = [label for needle, label in SIGNAL_LABELS.items() if needle in text]
    unique = list(dict.fromkeys(signals))
    if "free audit" in unique and "audit" in unique:
        unique.remove("audit")
    return unique[:limit]


def _domain_from_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    domain = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def classify_page_intent(url: str, title: str = "") -> str:
    text = f"{url} {title}".lower()
    if "llms.txt" in text or "router" in text:
        return "llms_router"
    if any(token in text for token in ["pricing", "price", "cost", "package", "worth"]):
        return "pricing"
    if any(token in text for token in ["case-study", "case-studies", "case_study", "success-story"]):
        return "case_studies"
    if any(token in text for token in ["audit", "checklist", "checker", "free-tools"]):
        return "audit_checklist"
    if "/blog" in text or "blog/" in text:
        return "blog"
    if "/about" in text or text.rstrip("/").endswith("about"):
        return "about"
    if any(token in text for token in ["service", "agency", "consult", "optimization", "optimisation", "get-found"]):
        return "services"
    if any(token in text for token in ["chatgpt", "perplexity", "gemini", "ai-overviews", "google-ai"]):
        return "platform_specific"
    if any(token in text for token in ["guide", "what-is", "geo-vs", "/kb/"]):
        return "guides"
    if any(token in text for token in ["location", "sydney", "australia"]):
        return "locations"
    return "other"


def _intent_focus(page_intent: str) -> str:
    focus = {
        "pricing": "Add price ranges, package comparison, ROI proof, risk reversal, and free-audit CTA.",
        "services": "Clarify service scope, deliverables, timeline, proof, and buyer-fit criteria.",
        "case_studies": "Add measurable outcomes, before/after evidence, implementation detail, and testimonial schema.",
        "blog": "Add answer-first summaries, stronger H2 matching, and links into commercial destination pages.",
        "about": "Add trust proof, team/market positioning, entity facts, and Organization schema.",
        "llms_router": "Keep routing strong but pass authority to destination pages with explicit internal links.",
        "audit_checklist": "Add step-by-step checks, examples, pass/fail criteria, FAQ, and checklist schema.",
        "platform_specific": "Add platform-specific retrieval/citation examples for ChatGPT, Perplexity, Gemini, and AI Overviews.",
        "guides": "Add concise definitions, comparison tables, examples, and links to service/pricing pages.",
        "locations": "Add local proof, Australian/Sydney examples, pricing expectations, and LocalBusiness schema.",
    }
    return focus.get(page_intent, "Add answer-first sections, competitor comparison, evidence, FAQ, schema, and internal links.")


def _schema_for_intent(page_intent: str) -> str:
    schemas = {
        "pricing": "FAQPage + Service + Offer",
        "services": "Service + FAQPage + BreadcrumbList",
        "case_studies": "Article + Review + Organization",
        "blog": "Article + FAQPage + BreadcrumbList",
        "about": "Organization + Person + BreadcrumbList",
        "llms_router": "WebSite + SiteNavigationElement",
        "audit_checklist": "FAQPage + HowTo + Checklist-style ItemList",
        "platform_specific": "Article + FAQPage",
        "guides": "Article + FAQPage + DefinedTerm",
        "locations": "LocalBusiness + Service + FAQPage",
    }
    return schemas.get(page_intent, "FAQPage + Article + BreadcrumbList")


def _faq_for_intent(page_intent: str, persona: str = "", stage: str = "") -> str:
    persona_text = f" for {persona}" if persona else ""
    stage_text = f" at {stage}" if stage else ""
    questions = {
        "pricing": [
            f"FAQ: How much does GEO cost{persona_text}?",
            "FAQ: What is included in each monthly package?",
            "FAQ: How do I validate ROI before committing?",
        ],
        "services": [
            f"FAQ: What does the GEO service include{persona_text}?",
            "FAQ: How long before AI visibility improves?",
            "FAQ: Which pages and schemas are implemented first?",
        ],
        "case_studies": [
            "FAQ: What changed before and after the GEO project?",
            "FAQ: Which metrics improved in AI answers?",
            "FAQ: What implementation work drove the lift?",
        ],
        "blog": [
            "FAQ: What should I do first after reading this guide?",
            "FAQ: Which AlphaXXXX service page should I use next?",
            "FAQ: How do I measure whether this advice worked?",
        ],
        "about": [
            "FAQ: Why trust AlphaXXXX for GEO?",
            "FAQ: Which markets and buyer types does AlphaXXXX serve?",
            "FAQ: How does AlphaXXXX measure AI visibility?",
        ],
        "llms_router": [
            "FAQ: Which page should AI systems cite for pricing?",
            "FAQ: Which page explains AlphaXXXX service fit?",
            "FAQ: Which page proves trust and outcomes?",
        ],
    }
    return " | ".join(questions.get(page_intent, [f"FAQ: What should {persona or 'buyers'} do next{stage_text}?", "FAQ: What proof supports this recommendation?", "FAQ: Which page should users visit next?"]))


def _internal_links_for_intent(page_intent: str) -> str:
    links = {
        "pricing": "Link from llms.txt, /buyers, /audit, service pages, and high-traffic blog posts to /geo-pricing.",
        "services": "Link from llms.txt, pricing, about, and related blog guides to the matching service page.",
        "case_studies": "Link from service, pricing, about, and proof sections into the strongest case study.",
        "blog": "Link from this blog to /geo-pricing, /audit, and the closest service page; link back from llms.txt if it answers a routed intent.",
        "about": "Link from llms.txt, footer, service pages, and comparison pages to /about for entity trust.",
        "llms_router": "Link from llms.txt to pricing, services, audit, about, and persona-specific pages with exact intent labels.",
        "audit_checklist": "Link from llms.txt, pricing, services, and blog diagnosis posts to /audit and checklist pages.",
    }
    return links.get(page_intent, "Link from llms.txt, related blog posts, services, pricing, audit, and about pages using descriptive anchors.")


def _markdown_cell(value: Any, max_len: int = 180) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = text.replace("|", "\\|")
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def _evidence_by_query(evidence_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("query_id") or ""): row for row in evidence_rows if row.get("query_id")}


def _rank_for_brand(chunks: list[dict[str, Any]], brand: str) -> int | None:
    target = brand.lower()
    for rank, chunk in enumerate(chunks, start=1):
        if str(chunk.get("brand") or "").lower() == target:
            return rank
    return None


def _first_non_target_chunk(chunks: list[dict[str, Any]], target_brand: str) -> dict[str, Any] | None:
    target = target_brand.lower()
    for chunk in chunks[:5]:
        if str(chunk.get("brand") or "").lower() != target:
            return chunk
    return None


def _join_sorted(values: set[str]) -> str:
    return ", ".join(sorted(value for value in values if value))


def build_url_top5_rankings(
    target_brand: str,
    evidence_rows: list[dict[str, Any]],
    limit: int = 25,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for evidence in evidence_rows:
        query_id = str(evidence.get("query_id") or "")
        model = str(evidence.get("model") or "")
        persona = str(evidence.get("persona") or "")
        stage = str(evidence.get("journey_stage") or "")
        chunks = evidence.get("retrieved_chunks") if isinstance(evidence.get("retrieved_chunks"), list) else []
        for rank, chunk in enumerate(chunks[:5], start=1):
            url = str(chunk.get("url") or "").strip()
            if not url:
                continue
            row = grouped.setdefault(
                url,
                {
                    "url": url,
                    "domain": _domain_from_url(url),
                    "brand": str(chunk.get("brand") or ""),
                    "title": str(chunk.get("title") or ""),
                    "source_type": str(chunk.get("source_type") or ""),
                    "query_ids": set(),
                    "top5_hit_count": 0,
                    "best_rank": rank,
                    "rank_sum": 0,
                    "models": set(),
                    "personas": set(),
                    "journey_stages": set(),
                    "signal_counter": Counter(),
                },
            )
            if not row["title"] and chunk.get("title"):
                row["title"] = str(chunk.get("title"))
            row["query_ids"].add(query_id)
            row["top5_hit_count"] += 1
            row["best_rank"] = min(int(row["best_rank"]), rank)
            row["rank_sum"] += rank
            if model:
                row["models"].add(model)
            if persona:
                row["personas"].add(persona)
            if stage:
                row["journey_stages"].add(stage)
            for signal in _signals_from_text(chunk.get("title"), chunk.get("text_preview"), limit=5):
                row["signal_counter"][signal] += 1

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        hit_count = int(row["top5_hit_count"])
        rows.append(
            {
                "rank": 0,
                "url": row["url"],
                "domain": row["domain"],
                "brand": row["brand"],
                "title": row["title"],
                "source_type": row["source_type"],
                "top5_query_count": len(row["query_ids"]),
                "top5_hit_count": hit_count,
                "best_rank": row["best_rank"],
                "avg_rank": round(float(row["rank_sum"]) / hit_count, 2) if hit_count else 0.0,
                "models": _join_sorted(row["models"]),
                "personas": _join_sorted(row["personas"]),
                "journey_stages": _join_sorted(row["journey_stages"]),
                "page_intent": classify_page_intent(str(row["url"]), str(row["title"])),
                "signals": ", ".join(signal for signal, _count in row["signal_counter"].most_common(5))
                or "semantic relevance",
            }
        )
    rows.sort(
        key=lambda item: (
            -int(item["top5_query_count"]),
            -int(item["top5_hit_count"]),
            int(item["best_rank"]),
            str(item["brand"]).lower() == target_brand.lower(),
            str(item["domain"]),
            str(item["url"]),
        )
    )
    for index, row in enumerate(rows[:limit], start=1):
        row["rank"] = index
    return rows[:limit]


def build_domain_top5_rankings(
    target_brand: str,
    evidence_rows: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    seen_query_domain: set[tuple[str, str]] = set()
    for evidence in evidence_rows:
        query_id = str(evidence.get("query_id") or "")
        model = str(evidence.get("model") or "")
        persona = str(evidence.get("persona") or "")
        stage = str(evidence.get("journey_stage") or "")
        chunks = evidence.get("retrieved_chunks") if isinstance(evidence.get("retrieved_chunks"), list) else []
        for rank, chunk in enumerate(chunks[:5], start=1):
            url = str(chunk.get("url") or "").strip()
            domain = _domain_from_url(url)
            if not domain:
                continue
            row = grouped.setdefault(
                domain,
                {
                    "domain": domain,
                    "brand_counter": Counter(),
                    "query_ids": set(),
                    "top5_hit_count": 0,
                    "best_rank": rank,
                    "rank_sum": 0,
                    "url_counter": Counter(),
                    "models": set(),
                    "personas": set(),
                    "journey_stages": set(),
                    "signal_counter": Counter(),
                },
            )
            if (query_id, domain) not in seen_query_domain:
                row["query_ids"].add(query_id)
                seen_query_domain.add((query_id, domain))
            row["top5_hit_count"] += 1
            row["best_rank"] = min(int(row["best_rank"]), rank)
            row["rank_sum"] += rank
            row["url_counter"][url] += 1
            row["brand_counter"][str(chunk.get("brand") or "")] += 1
            if model:
                row["models"].add(model)
            if persona:
                row["personas"].add(persona)
            if stage:
                row["journey_stages"].add(stage)
            for signal in _signals_from_text(chunk.get("title"), chunk.get("text_preview"), limit=5):
                row["signal_counter"][signal] += 1

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        hit_count = int(row["top5_hit_count"])
        rows.append(
            {
                "rank": 0,
                "domain": row["domain"],
                "brand": row["brand_counter"].most_common(1)[0][0] if row["brand_counter"] else "",
                "top5_query_count": len(row["query_ids"]),
                "top5_hit_count": hit_count,
                "best_rank": row["best_rank"],
                "avg_rank": round(float(row["rank_sum"]) / hit_count, 2) if hit_count else 0.0,
                "top_urls": "; ".join(url for url, _count in row["url_counter"].most_common(3)),
                "models": _join_sorted(row["models"]),
                "personas": _join_sorted(row["personas"]),
                "journey_stages": _join_sorted(row["journey_stages"]),
                "signals": ", ".join(signal for signal, _count in row["signal_counter"].most_common(5))
                or "semantic relevance",
            }
        )
    rows.sort(
        key=lambda item: (
            -int(item["top5_query_count"]),
            -int(item["top5_hit_count"]),
            int(item["best_rank"]),
            str(item["brand"]).lower() == target_brand.lower(),
            str(item["domain"]),
        )
    )
    for index, row in enumerate(rows[:limit], start=1):
        row["rank"] = index
    return rows[:limit]


def _evidence_lookup(evidence_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for evidence in evidence_rows:
        query_id = str(evidence.get("query_id") or "")
        model = str(evidence.get("model") or "")
        if query_id:
            lookup[(query_id, model)] = evidence
            lookup.setdefault((query_id, ""), evidence)
    return lookup


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def build_persona_stage_losses(
    target_brand: str,
    retrieval_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup = _evidence_lookup(evidence_rows)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    target = target_brand.lower()
    for retrieval in retrieval_rows:
        persona = str(retrieval.get("persona") or "")
        stage = str(retrieval.get("journey_stage") or "")
        key = (persona, stage)
        row = grouped.setdefault(
            key,
            {
                "persona": persona,
                "journey_stage": stage,
                "query_count": 0,
                "target_top5_count": 0,
                "not_ranked_count": 0,
                "winner_counter": Counter(),
                "domain_counter": Counter(),
                "url_counter": Counter(),
                "signal_counter": Counter(),
            },
        )
        row["query_count"] += 1
        if _truthy(retrieval.get("own_brand_in_top_5")):
            row["target_top5_count"] += 1
        if not str(retrieval.get("own_brand_rank") or "").strip():
            row["not_ranked_count"] += 1
        winner = str(retrieval.get("winning_brand") or "")
        if winner and winner.lower() != target:
            row["winner_counter"][winner] += 1
        evidence = lookup.get((str(retrieval.get("query_id") or ""), str(retrieval.get("model") or ""))) or lookup.get(
            (str(retrieval.get("query_id") or ""), "")
        )
        chunks = evidence.get("retrieved_chunks") if isinstance((evidence or {}).get("retrieved_chunks"), list) else []
        displacer = _first_non_target_chunk(chunks, target_brand) or {}
        url = str(displacer.get("url") or "")
        domain = _domain_from_url(url)
        if domain and not _truthy(retrieval.get("own_brand_in_top_5")):
            row["domain_counter"][domain] += 1
            row["url_counter"][url] += 1
            for signal in _signals_from_text(displacer.get("title"), displacer.get("text_preview"), limit=5):
                row["signal_counter"][signal] += 1

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        query_count = int(row["query_count"])
        target_top5 = int(row["target_top5_count"])
        winner, winner_count = row["winner_counter"].most_common(1)[0] if row["winner_counter"] else ("", 0)
        top_domain, _domain_count = row["domain_counter"].most_common(1)[0] if row["domain_counter"] else ("", 0)
        top_url, top_url_count = row["url_counter"].most_common(1)[0] if row["url_counter"] else ("", 0)
        reasons = ", ".join(signal for signal, _count in row["signal_counter"].most_common(5)) or "semantic relevance"
        rows.append(
            {
                "persona": row["persona"],
                "journey_stage": row["journey_stage"],
                "query_count": query_count,
                "target_top5_count": target_top5,
                "target_top5_share": round((target_top5 / query_count * 100) if query_count else 0.0, 2),
                "not_ranked_count": int(row["not_ranked_count"]),
                "leading_winner": winner,
                "winner_count": winner_count,
                "top_displacing_domain": top_domain,
                "top_displacing_url": top_url,
                "top_displacing_url_count": top_url_count,
                "primary_loss_reasons": reasons,
                "recommended_action": _recommended_action_for_loss(reasons, row["persona"], row["journey_stage"]),
            }
        )
    return sorted(rows, key=lambda item: (float(item["target_top5_share"]), -int(item["query_count"]), item["persona"], item["journey_stage"]))


def _recommended_action_for_loss(reasons: str, persona: str, stage: str) -> str:
    text = reasons.lower()
    if "pricing" in text or "cost" in text:
        return f"Build pricing and package proof for {persona or 'this persona'} in {stage or 'this stage'} queries."
    if "free audit" in text or "audit" in text:
        return "Strengthen audit/checklist pages with clear pass-fail examples and a low-risk CTA."
    if "sydney" in text or "australia" in text:
        return "Add Australian/local proof, Sydney examples, and local service schema to matching pages."
    if "chatgpt" in text or "perplexity" in text or "ai overviews" in text:
        return "Add platform-specific retrieval, citation, and monitoring examples."
    return "Create answer-first sections and internal links to the closest commercial page."


def build_page_intent_weakness_groups(
    top_pages: list[dict[str, Any]],
    weak_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for page in top_pages + weak_pages:
        url = str(page.get("url") or "")
        if not url:
            continue
        current = by_url.setdefault(url, dict(page))
        current.update({key: page.get(key, current.get(key)) for key in page})

    grouped: dict[str, dict[str, Any]] = {}
    weak_urls = {str(page.get("url") or "") for page in weak_pages}
    for url, page in by_url.items():
        intent = classify_page_intent(url, str(page.get("title") or ""))
        row = grouped.setdefault(
            intent,
            {
                "page_intent": intent,
                "page_count": 0,
                "weak_page_count": 0,
                "zero_top5_count": 0,
                "total_top5_queries": 0,
                "strongest": ("", -1),
                "weakest": [],
            },
        )
        top5_queries = int(page.get("top5_query_count") or 0)
        row["page_count"] += 1
        row["total_top5_queries"] += top5_queries
        if url in weak_urls:
            row["weak_page_count"] += 1
            row["weakest"].append((top5_queries, url))
        if top5_queries == 0:
            row["zero_top5_count"] += 1
        if top5_queries > row["strongest"][1]:
            row["strongest"] = (url, top5_queries)

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        weakest_urls = "; ".join(url for _count, url in sorted(row["weakest"])[:3])
        rows.append(
            {
                "page_intent": row["page_intent"],
                "page_count": row["page_count"],
                "weak_page_count": row["weak_page_count"],
                "zero_top5_count": row["zero_top5_count"],
                "total_top5_queries": row["total_top5_queries"],
                "strongest_url": row["strongest"][0],
                "weakest_urls": weakest_urls,
                "recommended_focus": _intent_focus(str(row["page_intent"])),
            }
        )
    return sorted(rows, key=lambda item: (-int(item["weak_page_count"]), -int(item["zero_top5_count"]), str(item["page_intent"])))


def _best_competitor_for_intent(page_intent: str, displacements: list[dict[str, Any]]) -> dict[str, Any]:
    for row in displacements:
        if classify_page_intent(str(row.get("winning_url") or ""), str(row.get("winning_title") or "")) == page_intent:
            return row
    return displacements[0] if displacements else {}


def build_content_optimization_actions(
    *,
    target_brand: str,
    weak_pages: list[dict[str, Any]],
    displacements: list[dict[str, Any]],
    persona_stage_losses: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    worst_loss = persona_stage_losses[0] if persona_stage_losses else {}
    rows: list[dict[str, Any]] = []
    for page in weak_pages[:limit]:
        url = str(page.get("url") or "")
        title = str(page.get("title") or "")
        page_intent = classify_page_intent(url, title)
        competitor = _best_competitor_for_intent(page_intent, displacements)
        top5 = int(page.get("top5_query_count") or 0)
        model_count = int(page.get("model_count") or 0)
        if top5 == 0:
            priority = "P0"
            problem = "No Top5 retrieval in this run"
            validation = "Top5 query count >= 5 in next standard run"
        elif model_count <= 1:
            priority = "P1"
            problem = "Retrieved by too few models"
            validation = "Retrieved by 2+ models and Top5 query count improves"
        else:
            priority = "P2"
            problem = "Retrieved but fragile"
            validation = "Maintain Top5 while improving model mention rate"
        rows.append(
            {
                "priority": priority,
                "url": url,
                "title": title,
                "page_intent": page_intent,
                "target_persona": str(worst_loss.get("persona") or ""),
                "target_stage": str(worst_loss.get("journey_stage") or ""),
                "problem": problem,
                "competitor_benchmark_url": str(competitor.get("winning_url") or ""),
                "competitor_benchmark_brand": str(competitor.get("winning_brand") or ""),
                "content_gaps": _intent_focus(page_intent),
                "internal_links_to_add": _internal_links_for_intent(page_intent),
                "faq_questions": _faq_for_intent(
                    page_intent,
                    str(worst_loss.get("persona") or ""),
                    str(worst_loss.get("journey_stage") or ""),
                ),
                "schema_recommendation": _schema_for_intent(page_intent),
                "validation_metric": validation,
            }
        )
    return rows


def build_query_loss_rows(
    target_brand: str,
    retrieval_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    limit: int = 30,
) -> list[dict[str, Any]]:
    evidence_map = _evidence_by_query(evidence_rows)
    rows: list[dict[str, Any]] = []
    for retrieval in retrieval_rows:
        winning_brand = str(retrieval.get("winning_brand") or "")
        if winning_brand.lower() == target_brand.lower():
            continue
        evidence = evidence_map.get(str(retrieval.get("query_id") or ""), {})
        chunks = evidence.get("retrieved_chunks") if isinstance(evidence.get("retrieved_chunks"), list) else []
        winner = _first_non_target_chunk(chunks, target_brand) or {}
        target_rank = _rank_for_brand(chunks, target_brand)
        rank_text = str(target_rank or retrieval.get("own_brand_rank") or "not ranked")
        signals = _signals_from_text(winner.get("title"), winner.get("text_preview"), limit=5)
        rows.append(
            {
                "query_id": str(retrieval.get("query_id") or ""),
                "query": str(retrieval.get("query") or evidence.get("query") or ""),
                "model": str(retrieval.get("model") or evidence.get("model") or ""),
                "persona": str(retrieval.get("persona") or evidence.get("persona") or ""),
                "journey_stage": str(retrieval.get("journey_stage") or evidence.get("journey_stage") or ""),
                "target_rank": rank_text,
                "winning_brand": str(winner.get("brand") or winning_brand or "Unknown"),
                "winning_url": str(winner.get("url") or ""),
                "winning_title": str(winner.get("title") or ""),
                "loss_reason": ", ".join(signals) or "stronger semantic/title match in Top5",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["target_rank"] == "not ranked",
            row["persona"],
            row["journey_stage"],
            row["model"],
            row["query_id"],
        ),
        reverse=True,
    )[:limit]


def build_competitor_displacements(
    target_brand: str,
    evidence_rows: list[dict[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    seen_query_url: set[tuple[str, str, str]] = set()
    target = target_brand.lower()
    for evidence in evidence_rows:
        chunks = evidence.get("retrieved_chunks") if isinstance(evidence.get("retrieved_chunks"), list) else []
        if _rank_for_brand(chunks[:5], target_brand) == 1:
            continue
        for chunk in chunks[:5]:
            brand = str(chunk.get("brand") or "")
            url = str(chunk.get("url") or "")
            if not brand or not url or brand.lower() == target:
                continue
            query_id = str(evidence.get("query_id") or "")
            dedupe_key = (query_id, brand, url)
            if dedupe_key in seen_query_url:
                continue
            seen_query_url.add(dedupe_key)
            key = (brand, url)
            row = grouped.setdefault(
                key,
                {
                    "winning_brand": brand,
                    "winning_url": url,
                    "winning_title": str(chunk.get("title") or ""),
                    "query_ids": set(),
                    "models": set(),
                    "personas": set(),
                    "journey_stages": set(),
                    "signal_counter": Counter(),
                },
            )
            row["query_ids"].add(query_id)
            if evidence.get("model"):
                row["models"].add(str(evidence.get("model")))
            if evidence.get("persona"):
                row["personas"].add(str(evidence.get("persona")))
            if evidence.get("journey_stage"):
                row["journey_stages"].add(str(evidence.get("journey_stage")))
            for signal in _signals_from_text(chunk.get("title"), chunk.get("text_preview"), limit=3):
                row["signal_counter"][signal] += 1

    rows: list[dict[str, Any]] = []
    for row in grouped.values():
        rows.append(
            {
                "winning_brand": row["winning_brand"],
                "winning_url": row["winning_url"],
                "winning_title": row["winning_title"],
                "top5_query_count": len(row["query_ids"]),
                "models": ", ".join(sorted(row["models"])),
                "personas": ", ".join(sorted(row["personas"])),
                "journey_stages": ", ".join(sorted(row["journey_stages"])),
                "signals": ", ".join(signal for signal, _count in row["signal_counter"].most_common(3))
                or "semantic relevance",
            }
        )
    return sorted(rows, key=lambda item: (-int(item["top5_query_count"]), item["winning_brand"], item["winning_url"]))[:limit]


def _recommended_modules_for_url(url: str) -> str:
    lower = url.lower()
    modules = []
    if "sydney" in lower or "local" in lower or "professional-services" in lower:
        modules.append("Sydney/local AI recommendation intent")
        modules.append("pricing/cost expectations")
        modules.append("free audit CTA")
    if "pricing" in lower or "cost" in lower or "worth" in lower:
        modules.append("price ranges and package comparison")
        modules.append("ROI objections")
    if "seo-agenc" in lower or "agency" in lower or "comparison" in lower:
        modules.append("agency comparison criteria")
        modules.append("questions before hiring")
    if "saas" in lower or "b2b" in lower:
        modules.append("B2B SaaS examples")
        modules.append("ChatGPT/Perplexity citation workflow")
    if "audit" in lower or "checklist" in lower:
        modules.append("step-by-step AI visibility audit")
        modules.append("checklist schema and pass/fail examples")
    if "blog" in lower:
        modules.append("answer-first summary")
        modules.append("internal links to matching money pages")
    if not modules:
        modules.extend(["clear answer-style H2s", "competitor comparison", "evidence and examples"])
    return "; ".join(list(dict.fromkeys(modules))[:5])


def build_page_optimization_plan(weak_pages: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in weak_pages[:limit]:
        top5 = int(page.get("top5_query_count") or 0)
        models = int(page.get("model_count") or 0)
        if top5 == 0:
            priority = "P0"
            problem = "No Top5 retrieval in this run"
            validation = "Top5 query count >= 5 in next standard run"
        elif top5 == 0 and models <= 1:
            priority = "P1"
            problem = "Retrieved by too few models"
            validation = "Retrieved by 2+ models and Top5 query count improves"
        else:
            priority = "P2"
            problem = "Retrieved but fragile"
            validation = "Maintain Top5 while improving model mention rate"
        rows.append(
            {
                "priority": priority,
                "url": str(page.get("url") or ""),
                "title": str(page.get("title") or ""),
                "problem": problem,
                "recommended_modules": _recommended_modules_for_url(str(page.get("url") or "")),
                "validation_metric": validation,
            }
        )
    return rows


def render_diagnostic_sections(
    *,
    target_brand: str,
    query_losses: list[dict[str, Any]],
    displacements: list[dict[str, Any]],
    page_plan: list[dict[str, Any]],
    source_run_count: int,
    answer_count: int,
    url_rankings: list[dict[str, Any]] | None = None,
    domain_rankings: list[dict[str, Any]] | None = None,
    persona_stage_losses: list[dict[str, Any]] | None = None,
    page_intent_groups: list[dict[str, Any]] | None = None,
    content_actions: list[dict[str, Any]] | None = None,
) -> str:
    top_displacement = displacements[0] if displacements else {}
    p0_pages = [row for row in page_plan if str(row.get("priority") or "") == "P0"]
    lines = [
        "## Executive Diagnosis",
        "",
        f"- This report uses {source_run_count} completed model run(s) and {answer_count} successful answer rows.",
        f"- The main question is not only whether {target_brand} was retrieved, but which competitor page displaced it for each buyer intent.",
        "- Treat the page plan below as a prioritized content backlog; validate changes by rerunning the same seeded scenario set.",
        "",
        f"## {target_brand} Weakness Diagnosis",
        "",
    ]
    if top_displacement:
        lines.append(
            f"- Competitor pages are repeatedly displacing {target_brand}; the strongest current displacement is "
            f"{top_displacement.get('winning_brand')} with {top_displacement.get('top5_query_count')} Top5 query hit(s)."
        )
    else:
        lines.append(f"- No repeated competitor displacement page was detected against {target_brand} in this run.")
    if p0_pages:
        lines.append(
            f"- {len(p0_pages)} owned page(s) had no Top5 retrieval in this run; prioritize pages that map to commercial, local, pricing, audit, and B2B SaaS intents."
        )
    else:
        lines.append("- No P0 owned-page retrieval gap was detected from the current weak-page table.")
    lines.extend(
        [
            "- The key fix is to make destination pages stronger, not only route more traffic through `llms.txt`: add answer-first summaries, comparison sections, evidence, pricing/free-audit language, and internal links from high-retrieval pages to money pages.",
            "- Validate improvements by rerunning the same seeded questions and watching model-level Recall@5 plus owned-page Top5 query count.",
        ]
    )

    if url_rankings is not None:
        lines.extend(
            [
                "",
                "## URL-Level Top5 Winners",
                "",
                "| Rank | URL | Domain | Brand | Top5 Queries | Best Rank | Intent | Signals |",
                "| ---: | --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        if url_rankings:
            for row in url_rankings[:15]:
                lines.append(
                    f"| {row['rank']} | {_markdown_cell(row['url'], 140)} | {_markdown_cell(row['domain'], 80)} | "
                    f"{_markdown_cell(row['brand'], 80)} | {row['top5_query_count']} | {row['best_rank']} | "
                    f"{_markdown_cell(row['page_intent'], 80)} | {_markdown_cell(row['signals'], 140)} |"
                )
        else:
            lines.append("| No URL-level Top5 rows were available. |  |  |  |  |  |  |  |")

    if domain_rankings is not None:
        lines.extend(
            [
                "",
                "## Domain-Level Top5 Winners",
                "",
                "| Rank | Domain | Brand | Top5 Queries | Best Rank | Top URLs | Signals |",
                "| ---: | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        if domain_rankings:
            for row in domain_rankings[:12]:
                lines.append(
                    f"| {row['rank']} | {_markdown_cell(row['domain'], 80)} | {_markdown_cell(row['brand'], 80)} | "
                    f"{row['top5_query_count']} | {row['best_rank']} | {_markdown_cell(row['top_urls'], 160)} | "
                    f"{_markdown_cell(row['signals'], 140)} |"
                )
        else:
            lines.append("| No domain-level Top5 rows were available. |  |  |  |  |  |  |")

    if persona_stage_losses is not None:
        lines.extend(
            [
                "",
                "## Persona/Stage Loss Matrix",
                "",
                "| Persona | Stage | Queries | AlphaXXXX Top5 | Not Ranked | Leading Winner | Top Displacing URL | Why Losing | Action |",
                "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        if persona_stage_losses:
            for row in persona_stage_losses[:12]:
                lines.append(
                    f"| {_markdown_cell(row['persona'], 80)} | {_markdown_cell(row['journey_stage'], 80)} | "
                    f"{row['query_count']} | {row['target_top5_share']}% | {row['not_ranked_count']} | "
                    f"{_markdown_cell(row['leading_winner'], 80)} | {_markdown_cell(row['top_displacing_url'], 140)} | "
                    f"{_markdown_cell(row['primary_loss_reasons'], 120)} | {_markdown_cell(row['recommended_action'], 160)} |"
                )
        else:
            lines.append("| No persona/stage loss rows were available. |  |  |  |  |  |  |  |  |")

    if page_intent_groups is not None:
        lines.extend(
            [
                "",
                "## Money Page Weakness Groups",
                "",
                "| Intent | Pages | Weak Pages | Zero Top5 | Total Top5 Queries | Weakest URLs | Recommended Focus |",
                "| --- | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        if page_intent_groups:
            for row in page_intent_groups[:12]:
                lines.append(
                    f"| {_markdown_cell(row['page_intent'], 80)} | {row['page_count']} | {row['weak_page_count']} | "
                    f"{row['zero_top5_count']} | {row['total_top5_queries']} | {_markdown_cell(row['weakest_urls'], 160)} | "
                    f"{_markdown_cell(row['recommended_focus'], 180)} |"
                )
        else:
            lines.append("| No page-intent weakness rows were available. |  |  |  |  |  |  |")

    if content_actions is not None:
        lines.extend(
            [
                "",
                "## Page-Level Action Plan",
                "",
                "| Priority | AlphaXXXX URL | Intent | Benchmark Competitor Page | Content Gaps | Internal Links | FAQ | Schema |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        if content_actions:
            for row in content_actions[:12]:
                lines.append(
                    f"| {row['priority']} | {_markdown_cell(row['url'], 130)} | {_markdown_cell(row['page_intent'], 80)} | "
                    f"{_markdown_cell(row['competitor_benchmark_url'], 130)} | {_markdown_cell(row['content_gaps'], 160)} | "
                    f"{_markdown_cell(row['internal_links_to_add'], 160)} | {_markdown_cell(row['faq_questions'], 180)} | "
                    f"{_markdown_cell(row['schema_recommendation'], 100)} |"
                )
        else:
            lines.append("| No content optimization action rows were available. |  |  |  |  |  |  |  |")

    lines.extend(
        [
        "",
        "## Query-Level Loss Analysis",
        "",
        "| Query | Model | Persona | Stage | Target Rank | Winning Brand | Winning URL | Why It Won |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    if query_losses:
        for row in query_losses[:15]:
            lines.append(
                f"| {_markdown_cell(row['query'])} | {_markdown_cell(row['model'], 80)} | "
                f"{_markdown_cell(row['persona'], 80)} | {_markdown_cell(row['journey_stage'], 80)} | "
                f"{_markdown_cell(row['target_rank'], 40)} | {_markdown_cell(row['winning_brand'], 80)} | "
                f"{_markdown_cell(row['winning_url'], 120)} | {_markdown_cell(row['loss_reason'], 120)} |"
            )
    else:
        lines.append(f"| No query-level losses were detected for {target_brand}. |  |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            f"## Competitor Pages Displacing {target_brand}",
            "",
            "| Competitor | URL | Top5 Queries | Models | Personas | Journey Stages | Repeated Signals |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    if displacements:
        for row in displacements[:15]:
            lines.append(
                f"| {_markdown_cell(row['winning_brand'], 80)} | {_markdown_cell(row['winning_url'], 140)} | "
                f"{row['top5_query_count']} | {_markdown_cell(row['models'], 120)} | "
                f"{_markdown_cell(row['personas'], 120)} | {_markdown_cell(row['journey_stages'], 120)} | "
                f"{_markdown_cell(row['signals'], 120)} |"
            )
    else:
        lines.append(f"| No competitor displacement pages were detected. |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Priority Optimization Plan",
            "",
            "| Priority | AlphaXXXX URL | Problem | Recommended Modules | Validation Metric |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if page_plan:
        for row in page_plan[:15]:
            lines.append(
                f"| {row['priority']} | {_markdown_cell(row['url'], 140)} | {_markdown_cell(row['problem'], 100)} | "
                f"{_markdown_cell(row['recommended_modules'], 180)} | {_markdown_cell(row['validation_metric'], 120)} |"
            )
    else:
        lines.append("| No owned pages were available for optimization planning. |  |  |  |  |")

    lines.extend(
        [
            "",
            "## Validation Plan For Next Run",
            "",
            "- Keep the same seeded questions when validating content changes.",
            "- Compare page-level Top5 query count before/after, not only the aggregate Recall@5.",
            "- Separate `llms.txt` routing lift from destination-page strength with a with/without corpus variant when the change is large.",
            "- Treat partial-model reports as directional unless all selected models complete.",
        ]
    )
    return "\n".join(lines) + "\n"
