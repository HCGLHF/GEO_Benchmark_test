from __future__ import annotations

import argparse
from pathlib import Path

from scripts.geo_eval.answers import evaluate_answers
from scripts.geo_eval.io import load_config, output_dir, read_csv
from scripts.geo_eval.models import run_models
from scripts.geo_eval.reports import write_report
from scripts.geo_eval.retrieval import evaluate_retrieval
from scripts.geo_eval.runner import generate_scenario_files, run_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic first-pass GEO evaluator.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "generate-scenarios",
        "plan-queries",
        "evaluate-retrieval",
        "run-models",
        "evaluate-answers",
        "report",
        "run-all",
    ):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", default="config/geo_evaluator.yaml")
    args = parser.parse_args()
    config = load_config(Path(args.config))
    run_dir = output_dir(config)

    if args.command in {"generate-scenarios", "plan-queries"}:
        generate_scenario_files(config)
        print(f"Wrote scenarios, query plans, and queries to {run_dir}")
    elif args.command == "evaluate-retrieval":
        rows = evaluate_retrieval(config, run_dir / "queries.csv", run_dir / "retrieval_evaluations.csv")
        print(f"Wrote retrieval evaluations for {len(rows)} queries to {run_dir / 'retrieval_evaluations.csv'}")
    elif args.command == "run-models":
        rows = run_models(config)
        print(f"Wrote or reused {len(rows)} model responses at {run_dir / 'model_responses.jsonl'}")
    elif args.command == "evaluate-answers":
        rows = evaluate_answers(config)
        print(f"Wrote answer evaluations for {len(rows)} responses to {run_dir / 'answer_evaluations.csv'}")
    elif args.command == "report":
        report = write_report(config, read_csv(run_dir / "retrieval_evaluations.csv"))
        print(f"Wrote summary to {run_dir / 'summary.md'} ({len(report.splitlines())} lines)")
    elif args.command == "run-all":
        run_all(config)
        print(f"Wrote GEO evaluator run to {run_dir}")
