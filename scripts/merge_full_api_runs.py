from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.client_acquisition_simulator import (
    ANSWER_FIELDS,
    API_CALL_SUMMARY_FIELDS,
    BRAND_PERFORMANCE_FIELDS,
    DIMENSION_FIELDS,
    QUERY_FIELDS,
    RETRIEVAL_FIELDS,
    build_api_call_summary,
    build_brand_performance_by_model,
    build_competitive_gap_report,
    build_dimension_breakdown,
    load_corpus_stats,
    write_csv,
)
from scripts.full_api_run_status import summarize_run_dirs
from scripts.geo_eval.io import load_config, read_csv, read_jsonl, write_jsonl
from scripts.page_drilldown import (
    build_owned_page_drilldown,
    load_owned_pages,
    render_owned_page_sections,
    write_page_drilldown_csv,
)
from scripts.report_diagnostics import (
    COMPETITOR_DISPLACEMENT_FIELDS,
    CONTENT_OPTIMIZATION_ACTION_FIELDS,
    DOMAIN_TOP5_FIELDS,
    PAGE_OPTIMIZATION_FIELDS,
    PAGE_INTENT_WEAKNESS_FIELDS,
    PERSONA_STAGE_LOSS_FIELDS,
    QUERY_LOSS_FIELDS,
    URL_TOP5_FIELDS,
    build_content_optimization_actions,
    build_competitor_displacements,
    build_domain_top5_rankings,
    build_page_optimization_plan,
    build_page_intent_weakness_groups,
    build_persona_stage_losses,
    build_query_loss_rows,
    build_url_top5_rankings,
    render_diagnostic_sections,
)


def read_optional_csv(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for row in read_csv(path)]


def read_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def write_manifest(output_dir: Path, run_dirs: list[Path], result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_runs": [str(path) for path in run_dirs],
        "result": result,
    }
    (output_dir / "merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_model_warning_section(warnings: list[dict[str, Any]]) -> str:
    if not warnings:
        return ""
    lines = ["## Model Warnings", ""]
    for warning in warnings:
        messages = [str(item) for item in warning.get("messages") or [] if str(item)]
        if not messages and warning.get("message"):
            messages = [str(warning["message"])]
        for message in messages:
            lines.append(f"- {message}")
    return "\n".join(lines) + "\n"


def merge_full_api_runs(
    run_dirs: list[Path],
    output_dir: Path,
    target_brand: str,
    configured_brands: list[str],
    corpus_stats: dict[str, dict[str, int]] | None = None,
    owned_pages: list[dict[str, Any]] | None = None,
    owned_documents_path: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    query_rows: list[dict[str, Any]] = []
    scenario_attempts: list[dict[str, Any]] = []
    rerank_attempts: list[dict[str, Any]] = []
    orchestrator_attempts: list[dict[str, Any]] = []
    retrieval_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []

    for run_dir in run_dirs:
        query_rows.extend(read_optional_csv(run_dir / "api_queries.csv"))
        scenario_attempts.extend(read_optional_jsonl(run_dir / "api_scenario_attempts.jsonl"))
        rerank_attempts.extend(read_optional_jsonl(run_dir / "api_rerank_attempts.jsonl"))
        orchestrator_attempts.extend(read_optional_jsonl(run_dir / "api_orchestrator_attempts.jsonl"))
        retrieval_rows.extend(read_optional_csv(run_dir / "retrieval_by_model.csv"))
        evidence_rows.extend(read_optional_jsonl(run_dir / "retrieval_evidence_by_model.jsonl"))
        answer_rows.extend(read_optional_csv(run_dir / "model_answer_evaluations.csv"))

    write_csv(output_dir / "api_queries.csv", query_rows, QUERY_FIELDS)
    write_jsonl(output_dir / "api_scenario_attempts.jsonl", scenario_attempts)
    write_jsonl(output_dir / "api_rerank_attempts.jsonl", rerank_attempts)
    write_jsonl(output_dir / "api_orchestrator_attempts.jsonl", orchestrator_attempts)
    write_csv(output_dir / "retrieval_by_model.csv", retrieval_rows, RETRIEVAL_FIELDS)
    write_jsonl(output_dir / "retrieval_evidence_by_model.jsonl", evidence_rows)
    write_csv(output_dir / "model_answer_evaluations.csv", answer_rows, ANSWER_FIELDS)

    brand_rows = build_brand_performance_by_model(
        target_brand=target_brand,
        configured_brands=configured_brands,
        retrieval_evidence=evidence_rows,
        answer_rows=answer_rows,
    )
    write_csv(output_dir / "brand_performance_by_model.csv", brand_rows, BRAND_PERFORMANCE_FIELDS)

    dimension_rows = build_dimension_breakdown(retrieval_rows, target_brand)
    write_csv(output_dir / "dimension_breakdown.csv", dimension_rows, DIMENSION_FIELDS)

    if orchestrator_attempts:
        write_csv(
            output_dir / "api_call_summary.csv",
            build_api_call_summary(orchestrator_attempts),
            API_CALL_SUMMARY_FIELDS,
        )

    report = build_competitive_gap_report(
        target_brand=target_brand,
        brand_rows=brand_rows,
        retrieval_rows=retrieval_rows,
        retrieval_evidence=evidence_rows,
        answer_rows=answer_rows,
        corpus_stats=corpus_stats if corpus_stats is not None else load_corpus_stats(),
    )
    pages = (
        owned_pages
        if owned_pages is not None
        else load_owned_pages(owned_documents_path or Path("data/processed/documents.jsonl"), target_brand)
    )
    page_drilldown = build_owned_page_drilldown(target_brand, evidence_rows, owned_pages=pages)
    write_page_drilldown_csv(output_dir / "owned_top5_pages.csv", page_drilldown.top_pages)
    write_page_drilldown_csv(output_dir / "owned_weak_pages.csv", page_drilldown.weak_pages)
    query_losses = build_query_loss_rows(target_brand, retrieval_rows, evidence_rows)
    displacements = build_competitor_displacements(target_brand, evidence_rows)
    page_plan = build_page_optimization_plan(page_drilldown.weak_pages)
    url_rankings = build_url_top5_rankings(target_brand, evidence_rows)
    domain_rankings = build_domain_top5_rankings(target_brand, evidence_rows)
    persona_stage_losses = build_persona_stage_losses(target_brand, retrieval_rows, evidence_rows)
    page_intent_groups = build_page_intent_weakness_groups(page_drilldown.top_pages, page_drilldown.weak_pages)
    content_actions = build_content_optimization_actions(
        target_brand=target_brand,
        weak_pages=page_drilldown.weak_pages,
        displacements=displacements,
        persona_stage_losses=persona_stage_losses,
    )
    write_csv(output_dir / "query_loss_analysis.csv", query_losses, QUERY_LOSS_FIELDS)
    write_csv(output_dir / "competitor_displacements.csv", displacements, COMPETITOR_DISPLACEMENT_FIELDS)
    write_csv(output_dir / "page_optimization_plan.csv", page_plan, PAGE_OPTIMIZATION_FIELDS)
    write_csv(output_dir / "url_top5_rankings.csv", url_rankings, URL_TOP5_FIELDS)
    write_csv(output_dir / "domain_top5_rankings.csv", domain_rankings, DOMAIN_TOP5_FIELDS)
    write_csv(output_dir / "persona_stage_losses.csv", persona_stage_losses, PERSONA_STAGE_LOSS_FIELDS)
    write_csv(output_dir / "page_intent_weakness.csv", page_intent_groups, PAGE_INTENT_WEAKNESS_FIELDS)
    write_csv(
        output_dir / "content_optimization_actions.csv",
        content_actions,
        CONTENT_OPTIMIZATION_ACTION_FIELDS,
    )
    (output_dir / "report_deep_diagnostics.json").write_text(
        json.dumps(
            {
                "url_top5_rankings": url_rankings,
                "domain_top5_rankings": domain_rankings,
                "persona_stage_losses": persona_stage_losses,
                "page_intent_groups": page_intent_groups,
                "content_optimization_actions": content_actions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    run_status = summarize_run_dirs(run_dirs)
    warning_section = render_model_warning_section(run_status.get("warnings") or [])
    report = (
        report.rstrip()
        + "\n\n"
        + (warning_section + "\n" if warning_section else "")
        + render_diagnostic_sections(
            target_brand=target_brand,
            query_losses=query_losses,
            displacements=displacements,
            page_plan=page_plan,
            source_run_count=len(run_dirs),
            answer_count=len([row for row in answer_rows if not row.get("error")]),
            url_rankings=url_rankings,
            domain_rankings=domain_rankings,
            persona_stage_losses=persona_stage_losses,
            page_intent_groups=page_intent_groups,
            content_actions=content_actions,
        )
        + "\n"
        + render_owned_page_sections(target_brand, page_drilldown)
    )
    (output_dir / "competitive_gap_report.md").write_text(report, encoding="utf-8")

    result = {
        "source_run_count": len(run_dirs),
        "query_rows": len(query_rows),
        "retrieval_rows": len(retrieval_rows),
        "evidence_rows": len(evidence_rows),
        "answer_rows": len(answer_rows),
        "brand_rows": len(brand_rows),
        "output_dir": str(output_dir),
        "model_warning_count": int(run_status.get("warning_count") or 0),
        "model_fatal_count": int(run_status.get("fatal_count") or 0),
    }
    write_manifest(output_dir, run_dirs, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge single-model full API runs into one report.")
    parser.add_argument("--config", default="config/client_acquisition_simulator.yaml")
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    campaign = config.get("campaign", {})
    result = merge_full_api_runs(
        run_dirs=[Path(item) for item in args.runs],
        output_dir=Path(args.output_dir),
        target_brand=str(campaign.get("target_brand", "")),
        configured_brands=[str(item) for item in campaign.get("competitors", [])],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nReport: {Path(result['output_dir']) / 'competitive_gap_report.md'}")


if __name__ == "__main__":
    main()
