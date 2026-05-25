from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


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
) -> str:
    lines = [
        "## Executive Diagnosis",
        "",
        f"- This report uses {source_run_count} completed model run(s) and {answer_count} successful answer rows.",
        f"- The main question is not only whether {target_brand} was retrieved, but which competitor page displaced it for each buyer intent.",
        "- Treat the page plan below as a prioritized content backlog; validate changes by rerunning the same seeded scenario set.",
        "",
        "## Query-Level Loss Analysis",
        "",
        "| Query | Model | Persona | Stage | Target Rank | Winning Brand | Winning URL | Why It Won |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
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
