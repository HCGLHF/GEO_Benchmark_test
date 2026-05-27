from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_eval.answers import (
    contains_domain,
    evaluate_answer_rows,
    evaluate_answers,
    model_key,
    model_summary_rows,
    percent,
    write_model_summary_markdown,
)
from scripts.geo_eval.cli import main
from scripts.geo_eval.io import (
    campaign_value,
    load_config,
    output_dir,
    read_csv,
    read_jsonl,
    safe_json_list,
    write_csv_rows,
    write_json,
    write_jsonl,
)
from scripts.geo_eval.models import (
    api_headers,
    build_chat_payload,
    build_direct_prompt,
    call_chat_model,
    direct_config,
    model_response_key,
    provider_endpoint,
    run_models,
    should_run_direct,
)
from scripts.geo_eval.reports import build_summary, write_report
from scripts.geo_eval.retrieval import (
    COMPACT_RETRIEVAL_FIELDS,
    compact_retrieval_row,
    evaluate_retrieval,
    evidence_row,
    insert_retrieval_sqlite,
    is_true,
    retrieval_summary,
    write_retrieval_outputs,
)
from scripts.geo_eval.runner import generate_scenario_files, run_all
from scripts.geo_eval.scenarios import (
    INTENT_TEMPLATES,
    QUERY_FAMILIES,
    competitor_pair,
    generate_query_plans,
    generate_scenarios,
    write_queries_csv,
)

__all__ = [
    "COMPACT_RETRIEVAL_FIELDS",
    "INTENT_TEMPLATES",
    "QUERY_FAMILIES",
    "api_headers",
    "build_chat_payload",
    "build_direct_prompt",
    "build_summary",
    "call_chat_model",
    "campaign_value",
    "compact_retrieval_row",
    "competitor_pair",
    "contains_domain",
    "direct_config",
    "evaluate_answer_rows",
    "evaluate_answers",
    "evaluate_retrieval",
    "evidence_row",
    "generate_query_plans",
    "generate_scenario_files",
    "generate_scenarios",
    "insert_retrieval_sqlite",
    "is_true",
    "load_config",
    "main",
    "model_key",
    "model_response_key",
    "model_summary_rows",
    "output_dir",
    "percent",
    "provider_endpoint",
    "read_csv",
    "read_jsonl",
    "retrieval_summary",
    "run_all",
    "run_models",
    "safe_json_list",
    "should_run_direct",
    "write_csv_rows",
    "write_json",
    "write_jsonl",
    "write_model_summary_markdown",
    "write_queries_csv",
    "write_report",
    "write_retrieval_outputs",
]


if __name__ == "__main__":
    main()
