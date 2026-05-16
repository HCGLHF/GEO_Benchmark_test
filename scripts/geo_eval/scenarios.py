from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.geo_eval.io import campaign_value


INTENT_TEMPLATES = [
    ("direct_recommendation", "What are the best {category} vendors for a {buyer_profile} in the {market} market?"),
    ("comparison", "Which {category} providers should a {buyer_profile} compare before buying?"),
    ("problem_led", "Why do competitors appear in AI answers while my company is missing, and what vendors can help?"),
    ("budget_stage", "What is a practical {category} option for a {buyer_profile} with a limited budget?"),
    ("trust_proof", "Which {category} vendors have strong proof, case studies, and reliable measurement?"),
    ("alternatives", "What are credible alternatives to {first_competitor} for AI search visibility?"),
]

QUERY_FAMILIES = [
    ("category_discovery", ["best generative engine optimization companies", "AI search visibility platform vendors"]),
    ("buyer_specific", ["generative engine optimization for {buyer_profile}", "AI answer monitoring tools for {buyer_profile}"]),
    ("competitor_comparison", ["{first_competitor} alternatives GEO platform", "{first_competitor} vs {second_competitor} AI search visibility"]),
    ("proof_credibility", ["GEO company case studies {buyer_profile}", "AI search visibility platform customer examples"]),
    ("pricing_packaging", ["GEO platform pricing", "AI search visibility software pricing"]),
    ("citation_strategy", ["how AI search engines cite vendor websites", "how to get cited in ChatGPT Perplexity AI Overviews"]),
]


def competitor_pair(config: dict[str, Any]) -> tuple[str, str]:
    competitors = config.get("campaign", {}).get("competitors") or ["competitor", "alternative vendor"]
    first = str(competitors[0]) if competitors else "competitor"
    second = str(competitors[1]) if len(competitors) > 1 else "alternative vendor"
    return first, second


def generate_scenarios(config: dict[str, Any]) -> list[dict[str, Any]]:
    campaign = config.get("campaign", {})
    run = config.get("run", {})
    buyer_profiles = campaign.get("buyer_profiles") or ["B2B marketing leader"]
    scenarios_per_profile = int(run.get("scenarios_per_profile", 5))
    first_competitor, _second_competitor = competitor_pair(config)
    scenarios: list[dict[str, Any]] = []

    for buyer_profile in buyer_profiles:
        for index in range(scenarios_per_profile):
            intent_family, template = INTENT_TEMPLATES[index % len(INTENT_TEMPLATES)]
            raw_question = template.format(
                category=campaign.get("category", "GEO"),
                buyer_profile=buyer_profile,
                market=campaign.get("market", "target"),
                first_competitor=first_competitor,
            )
            scenarios.append(
                {
                    "id": f"sc{len(scenarios) + 1:03d}",
                    "campaign_id": campaign.get("name", "geo_campaign"),
                    "intent_family": intent_family,
                    "buyer_profile": buyer_profile,
                    "raw_question": raw_question,
                    "ambiguity_notes": "Assumes GEO means Generative Engine Optimization, not geospatial.",
                    "rewritten_task": (
                        f"Find and compare {campaign.get('category', 'GEO')} vendors for {buyer_profile} "
                        f"in the {campaign.get('market', 'target')} market. Evaluate capabilities, proof, "
                        "pricing transparency, customer fit, citation potential, and whether each vendor is "
                        "suitable as a recommended option."
                    ),
                }
            )
    return scenarios


def generate_query_plans(config: dict[str, Any], scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_competitor, second_competitor = competitor_pair(config)
    category = campaign_value(config, "category", "GEO")
    plans: list[dict[str, Any]] = []
    for scenario in scenarios:
        queries: list[dict[str, Any]] = [
            {
                "query": scenario["raw_question"],
                "intent": "scenario_question",
                "expected_evidence": ["natural model answer", "vendor recommendations"],
                "priority": 0,
            },
            {
                "query": f"{category} {scenario.get('buyer_profile', 'buyer')} {scenario.get('intent_family', '')}",
                "intent": "scenario_context",
                "expected_evidence": ["vendor pages", "comparison pages"],
                "priority": 1,
            },
        ]
        for priority, (intent, templates) in enumerate(QUERY_FAMILIES, start=1):
            for template in templates:
                queries.append(
                    {
                        "query": template.format(
                            buyer_profile=scenario.get("buyer_profile", "buyer"),
                            first_competitor=first_competitor,
                            second_competitor=second_competitor,
                        ),
                        "intent": intent,
                        "expected_evidence": ["vendor pages", "comparison pages", "case studies"],
                        "priority": priority,
                    }
                )
        plans.append({"id": f"qp{len(plans) + 1:03d}", "scenario_id": scenario["id"], "created_by_model": "template:v1", "queries": queries})
    return plans


def write_queries_csv(path: Path, config: dict[str, Any], query_plans: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    target_brand = campaign_value(config, "target_brand")
    for plan in query_plans:
        for query in plan.get("queries", []):
            query_text = str(query["query"])
            if query_text in seen:
                continue
            seen.add(query_text)
            rows.append(
                {
                    "query_id": f"q{len(rows) + 1:03d}",
                    "query": query_text,
                    "intent": str(query.get("intent", "")),
                    "priority": str(query.get("priority", "")),
                    "target_brand": target_brand,
                    "notes": f"Generated from {plan['scenario_id']} by GeoEvaluator template planner",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query_id", "query", "intent", "priority", "target_brand", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    return rows
