from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.geo_eval.io import campaign_value, output_dir, read_jsonl, write_csv_rows
from scripts.geo_eval.retrieval import is_true


def contains_domain(values: list[Any], domain: str) -> bool:
    normalized_domain = domain.lower().removeprefix("www.")
    for value in values:
        raw = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
        if normalized_domain and normalized_domain in raw.lower().removeprefix("www."):
            return True
    return False


def evaluate_answer_rows(config: dict[str, Any], responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_brand = campaign_value(config, "target_brand")
    target_domain = campaign_value(config, "target_domain")
    competitors = [str(item) for item in config.get("campaign", {}).get("competitors", [])]
    rows: list[dict[str, Any]] = []
    for response in responses:
        answer = str(response.get("raw_answer", ""))
        if response.get("error") or not answer:
            continue
        answer_lower = answer.lower()
        target_lower = target_brand.lower()
        citations = response.get("citations") or []
        competitor_mentions = [competitor for competitor in competitors if competitor.lower() in answer_lower]
        mentioned = target_lower in answer_lower
        rows.append(
            {
                "response_id": response.get("response_id", ""),
                "query_id": response.get("query_id", ""),
                "provider": response.get("provider", ""),
                "model": response.get("model", ""),
                "mode": response.get("mode", ""),
                "repeat_index": response.get("repeat_index", 0),
                "brand_mentioned": str(mentioned),
                "mention_count": answer_lower.count(target_lower),
                "cited_own_url": str(contains_domain(citations, target_domain) or target_domain.lower() in answer_lower),
                "recommended_own_brand": str(mentioned and "recommend" in answer_lower),
                "competitors_mentioned_json": json.dumps(competitor_mentions, ensure_ascii=False),
                "citations_json": json.dumps(citations, ensure_ascii=False),
                "answer_coverage_score": 1 if answer else 0,
            }
        )
    return rows


def evaluate_answers(config: dict[str, Any]) -> list[dict[str, Any]]:
    run_dir = output_dir(config)
    responses = read_jsonl(run_dir / "model_responses.jsonl")
    rows = evaluate_answer_rows(config, responses)
    write_csv_rows(
        run_dir / "answer_evaluations.csv",
        rows,
        [
            "response_id",
            "query_id",
            "provider",
            "model",
            "mode",
            "repeat_index",
            "brand_mentioned",
            "mention_count",
            "cited_own_url",
            "recommended_own_brand",
            "competitors_mentioned_json",
            "citations_json",
            "answer_coverage_score",
        ],
    )
    summaries = model_summary_rows(rows, responses)
    write_csv_rows(
        run_dir / "model_summary_by_llm.csv",
        summaries,
        [
            "provider",
            "model",
            "mode",
            "total_requests",
            "successful_responses",
            "total_answers",
            "success_rate",
            "brand_mention_rate",
            "citation_rate",
            "recommendation_rate",
            "average_answer_coverage",
        ],
    )
    write_model_summary_markdown(config, summaries, run_dir / "model_summary.md")
    return summaries


def percent(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator if denominator else 0.0):.1%}"


def model_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("provider", "")), str(row.get("model", "")), str(row.get("mode", "direct")))


def model_summary_rows(evaluations: list[dict[str, Any]], responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({model_key(row) for row in responses} | {model_key(row) for row in evaluations})
    rows: list[dict[str, Any]] = []
    for provider, model, mode in keys:
        response_group = [row for row in responses if model_key(row) == (provider, model, mode)]
        eval_group = [row for row in evaluations if model_key(row) == (provider, model, mode)]
        total_requests = len(response_group)
        successful = sum(1 for row in response_group if not row.get("error"))
        total_answers = len(eval_group)
        brand_mentions = sum(is_true(row.get("brand_mentioned")) for row in eval_group)
        citations = sum(is_true(row.get("cited_own_url")) for row in eval_group)
        recommendations = sum(is_true(row.get("recommended_own_brand")) for row in eval_group)
        coverage_scores = [int(row.get("answer_coverage_score") or 0) for row in eval_group]
        rows.append(
            {
                "provider": provider,
                "model": model,
                "mode": mode,
                "total_requests": total_requests,
                "successful_responses": successful,
                "total_answers": total_answers,
                "success_rate": percent(successful, total_requests),
                "brand_mention_rate": percent(brand_mentions, total_answers),
                "citation_rate": percent(citations, total_answers),
                "recommendation_rate": percent(recommendations, total_answers),
                "average_answer_coverage": f"{(sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0.0):.2f}",
            }
        )
    return sorted(
        rows,
        key=lambda row: (-int(row["total_answers"]), -int(row["successful_responses"]), row["provider"], row["model"], row["mode"]),
    )


def write_model_summary_markdown(config: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        f"# Model Summary: {campaign_value(config, 'target_brand', 'Target')}",
        "",
        "## Context Policy",
        "",
        "- Each API call is sent as a clean, standalone chat request.",
        "- No previous model answer or chat history is included unless a future mode explicitly adds context.",
        "- Metrics are grouped per provider/model/mode so model-specific GEO performance stays separate.",
        "",
        "## Models",
        "",
    ]
    if rows:
        lines.append("| Provider | Model | Mode | Success | Brand Mention | Citation | Recommendation |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                f"| {row['provider']} | {row['model']} | {row['mode']} | {row['success_rate']} | "
                f"{row['brand_mention_rate']} | {row['citation_rate']} | {row['recommendation_rate']} |"
            )
    else:
        lines.append("- No model responses available.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
