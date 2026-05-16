from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.geo_eval.io import campaign_value, output_dir, safe_json_list
from scripts.geo_eval.retrieval import is_true, retrieval_summary


def build_summary(config: dict[str, Any], retrieval_rows: list[dict[str, str]]) -> str:
    target_brand = campaign_value(config, "target_brand", "target brand")
    summary = retrieval_summary(retrieval_rows)
    lines = [f"# GEO Evaluator Summary: {target_brand}", "", "## Configured Models", ""]
    models = config.get("models") or []
    if models:
        for model in models:
            lines.append(f"- {model.get('provider', '')}/{model.get('model', '')}")
    else:
        lines.append("- No model configured.")
    lines.extend(
        [
            "- Context policy: clean per API call",
            "",
            "## Retrieval Metrics",
            "",
            f"- Queries evaluated: {summary['query_count']}",
            f"- Recall@5: {summary['recall_at_5']:.1%}",
            f"- Competitor Win Rate: {summary['competitor_win_rate']:.1%}",
            f"- Own brand ranked in Top K: {summary['own_brand_ranked_count']}/{summary['query_count']}",
        ]
    )
    if summary["average_own_brand_rank"] is not None:
        lines.append(f"- Average own brand rank: {summary['average_own_brand_rank']:.2f}")
    else:
        lines.append("- Average own brand rank: not ranked")

    lines.extend(["", "## Weak Queries", ""])
    weak_rows = [row for row in retrieval_rows if not is_true(row.get("own_brand_in_top_5"))]
    if weak_rows:
        for row in weak_rows[:25]:
            lines.append(f"- `{row.get('query_id')}` {row.get('query')}")
            urls = safe_json_list(row.get("matched_urls_json", ""))[:5]
            for index, url in enumerate(urls, start=1):
                lines.append(f"  {index}. {url}")
    else:
        lines.append("- No weak queries found for Recall@5.")

    lines.extend(["", "## Notes", ""])
    status_path = output_dir(config) / "model_run_status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        lines.extend(
            [
                f"- Direct model run: {status.get('reason')}",
                f"- Direct Recall@5 gate: {status.get('recall_at_5', 0):.1%} / {status.get('min_recall_at_5', 0.5):.1%}",
            ]
        )
    lines.append("- Direct model calls run only when the configured Recall@5 gate allows them.")
    lines.append("- Answer evaluation can run on any existing model responses and does not use the Recall@5 gate.")
    lines.append("- Scenario and query generation use deterministic templates for reproducibility.")
    return "\n".join(lines) + "\n"


def write_report(config: dict[str, Any], retrieval_rows: list[dict[str, str]]) -> str:
    report = build_summary(config, retrieval_rows)
    path = output_dir(config) / "summary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return report
