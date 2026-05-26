from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.watch_full_api_run import summarize_run


PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "google": "Google",
    "perplexity": "Perplexity",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "x-ai": "xAI",
    "bytedance-seed": "Doubao",
}


def display_model_family(model: str, safe_name: str = "") -> str:
    value = model or safe_name
    provider = value.split("/", 1)[0].split("_", 1)[0].strip().lower()
    return PROVIDER_DISPLAY_NAMES.get(provider, provider.title() if provider else "Unknown model")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _failure_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    return [dict(row) for row in summary.get("failures") or []]


def _all_failure_rows(run_dir: Path, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    path = run_dir / "api_orchestrator_attempts.jsonl"
    if not path.exists():
        return fallback
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("status") or "").lower() == "error":
                rows.append(
                    {
                        "task_type": str(row.get("task_type") or ""),
                        "model": str(row.get("model") or ""),
                        "query_id": str(row.get("query_id") or ""),
                        "error": str(row.get("error") or ""),
                    }
                )
    return rows or fallback


def _rate_limit_count(failures: list[dict[str, str]]) -> int:
    return sum(1 for row in failures if "429" in str(row.get("error") or "") or "rate limit" in str(row.get("error") or "").lower())


def _outputs_complete(summary: dict[str, Any]) -> bool:
    missing = summary.get("missing") or {}
    totals = summary.get("totals") or {}
    return (
        int(totals.get("queries") or 0) > 0
        and int(missing.get("queries") or 0) == 0
        and int(missing.get("retrieval_rows") or 0) == 0
        and int(missing.get("answer_rows") or 0) == 0
    )


def summarize_run_dir(run_dir: Path | str, exit_code: int | str | None = None) -> dict[str, Any]:
    path = Path(run_dir)
    summary = summarize_run(path)
    safe_name = path.name
    model = ""
    for failure in _failure_rows(summary):
        if failure.get("model"):
            model = str(failure["model"])
            break
    if not model:
        models = list((summary.get("models") or {}).keys())
        model = str(models[0]) if models else safe_name.replace("_", "/")

    exit_text = "" if exit_code is None else str(exit_code).strip()
    failures = _all_failure_rows(path, _failure_rows(summary))
    failure_count = int((summary.get("totals") or {}).get("failures") or 0)
    rate_limit_failures = _rate_limit_count(failures)
    complete_outputs = _outputs_complete(summary)
    missing = summary.get("missing") or {}
    display_name = display_model_family(model, safe_name)

    messages: list[str] = []
    fatal = False
    warning = False

    if not complete_outputs:
        fatal = True
        missing_parts = []
        if int(missing.get("retrieval_rows") or 0):
            missing_parts.append(f"{missing.get('retrieval_rows')} missing retrieval rows")
        if int(missing.get("answer_rows") or 0):
            missing_parts.append(f"{missing.get('answer_rows')} missing answer rows")
        if not missing_parts:
            missing_parts.append("incomplete outputs")
        messages.append(f"{safe_name} has {', '.join(missing_parts)}.")
    elif failure_count > 0 or (exit_text and exit_text != "0"):
        warning = True
        if rate_limit_failures:
            messages.append(
                f"{display_name} had {rate_limit_failures} rate-limit {_plural(rate_limit_failures, 'failure')}; interpret with caution."
            )
        non_rate_limit = max(failure_count - rate_limit_failures, 0)
        if non_rate_limit:
            messages.append(
                f"{display_name} had {non_rate_limit} API {_plural(non_rate_limit, 'failure')}; interpret with caution."
            )
        if exit_text and exit_text != "0":
            messages.append(f"{display_name} worker exited with code {exit_text}, but complete outputs are present.")

    return {
        "run_dir": str(path),
        "safe_name": safe_name,
        "model": model,
        "display_name": display_name,
        "exit_code": exit_text,
        "complete_outputs": complete_outputs,
        "failure_count": failure_count,
        "rate_limit_failures": rate_limit_failures,
        "fatal": fatal,
        "warning": warning,
        "message": " ".join(messages),
        "messages": messages,
        "summary": summary,
    }


def summarize_run_dirs(run_dirs: list[Path | str], exit_codes: dict[str, int | str] | None = None) -> dict[str, Any]:
    exit_codes = exit_codes or {}
    models = []
    for run_dir in run_dirs:
        path = Path(run_dir)
        models.append(summarize_run_dir(path, exit_codes.get(path.name)))
    fatals = [model for model in models if model["fatal"]]
    warnings = [model for model in models if model["warning"]]
    status = "failed" if fatals else "complete_with_model_warnings" if warnings else "complete"
    return {
        "status": status,
        "fatal_count": len(fatals),
        "warning_count": len(warnings),
        "fatals": fatals,
        "warnings": warnings,
        "models": models,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify completed full API model runs as fatal, warning, or clean.")
    parser.add_argument("--run-dir", action="append", required=True)
    parser.add_argument("--exit-code-json", default="{}")
    parser.add_argument("--exit-code-file", default="")
    args = parser.parse_args()
    if args.exit_code_file:
        exit_codes = json.loads(Path(args.exit_code_file).read_text(encoding="utf-8-sig"))
    else:
        exit_codes = json.loads(args.exit_code_json)
    result = summarize_run_dirs([Path(item) for item in args.run_dir], exit_codes=exit_codes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
