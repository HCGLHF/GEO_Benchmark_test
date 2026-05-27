from __future__ import annotations

from typing import Any

from scripts.geo_eval.answers import evaluate_answers
from scripts.geo_eval.io import output_dir, write_json
from scripts.geo_eval.models import run_models
from scripts.geo_eval.reports import write_report
from scripts.geo_eval.retrieval import evaluate_retrieval
from scripts.geo_eval.scenarios import generate_query_plans, generate_scenarios, write_queries_csv


def generate_scenario_files(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    run_dir = output_dir(config)
    scenarios = generate_scenarios(config)
    plans = generate_query_plans(config, scenarios)
    queries = write_queries_csv(run_dir / "queries.csv", config, plans)
    write_json(run_dir / "scenarios.json", scenarios)
    write_json(run_dir / "query_plans.json", plans)
    write_json(run_dir / "run_config.resolved.json", config)
    return scenarios, plans, queries


def run_all(config: dict[str, Any]) -> None:
    run_dir = output_dir(config)
    generate_scenario_files(config)
    rows = evaluate_retrieval(config, run_dir / "queries.csv", run_dir / "retrieval_evaluations.csv")
    run_models(config)
    evaluate_answers(config)
    write_report(config, rows)
