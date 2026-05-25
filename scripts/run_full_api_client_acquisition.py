from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import load_dotenv
from scripts.client_acquisition_simulator import run_simulator
from scripts.geo_eval.io import load_config


def timestamped_output_dir() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"runs/client_acquisition_simulator_full_api_{stamp}"


def selected_models(config: dict[str, Any], include_models: list[str], exclude_models: list[str]) -> list[dict[str, Any]]:
    models = list(config.get("models", []) or [])
    if include_models:
        wanted = set(include_models)
        models = [model for model in models if str(model.get("model", "")) in wanted]
    if exclude_models:
        blocked = set(exclude_models)
        models = [model for model in models if str(model.get("model", "")) not in blocked]
    return models


def prepare_config(args: argparse.Namespace) -> dict[str, Any]:
    config = copy.deepcopy(load_config(Path(args.config)))
    run_config = config.setdefault("run", {})
    run_config["output_dir"] = args.output_dir or timestamped_output_dir()
    if getattr(args, "ops_run_root", None):
        run_config["ops_run_root"] = args.ops_run_root

    if args.queries_per_model is not None:
        config.setdefault("client_acquisition", {})["queries_per_model"] = args.queries_per_model

    config["models"] = selected_models(config, args.include_model, args.exclude_model)
    if not config["models"]:
        raise SystemExit("No models selected. Check --include-model / --exclude-model.")

    performance = config.setdefault("performance", {})
    performance.setdefault("llm_cache", {}).setdefault("enabled", True)
    performance.setdefault("llm_cache", {}).setdefault("sqlite", "data/cache/llm_calls.sqlite")
    if getattr(args, "cache_path", None):
        performance["llm_cache"]["sqlite"] = args.cache_path
    performance.setdefault("run_state", {})["enabled"] = True
    performance["run_state"]["sqlite"] = str(Path(run_config["output_dir"]) / "run_state.sqlite")
    return config


def verify_api_keys(config: dict[str, Any]) -> None:
    load_dotenv()
    missing = sorted(
        {
            str(model.get("api_key_env", "OPENAI_API_KEY"))
            for model in config.get("models", [])
            if not os.environ.get(str(model.get("api_key_env", "OPENAI_API_KEY")))
        }
    )
    if missing:
        raise SystemExit(f"Missing required API key environment variables: {', '.join(missing)}")


def write_resolved_config(config: dict[str, Any]) -> None:
    run_dir = Path(config["run"]["output_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_config.resolved.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the highest-fidelity client acquisition simulator with external model APIs. "
            "This sends retrieved corpus excerpts to the configured model providers."
        )
    )
    parser.add_argument("--config", default="config/client_acquisition_simulator.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--queries-per-model", type=int, default=None)
    parser.add_argument("--include-model", action="append", default=[])
    parser.add_argument("--exclude-model", action="append", default=[])
    parser.add_argument("--cache-path", default=None, help="Override the LLM cache SQLite path for this run.")
    parser.add_argument("--ops-run-root", default=None, help="Write ops events to this parent run root.")
    args = parser.parse_args()

    config = prepare_config(args)
    verify_api_keys(config)
    write_resolved_config(config)
    result = run_simulator(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nReport: {Path(result['run_dir']) / 'competitive_gap_report.md'}")


if __name__ == "__main__":
    main()
