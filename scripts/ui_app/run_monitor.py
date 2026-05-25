from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.full_api_run_status import summarize_run_dir
from scripts.ops_logging import read_summary
from scripts.pipeline_state import read_pipeline_status
from scripts.ui_app.report_summary import summarize_latest_report
from scripts.watch_full_api_run import summarize_run


def _tail_lines(path: Path, max_lines: int = 40) -> list[str]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    elif raw[:200].count(b"\x00") > 20:
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    return lines[-max_lines:]


def _model_dirs(run_root: Path) -> list[Path]:
    if not run_root.exists():
        return []
    ignored = {"cache", "merged"}
    return sorted(path for path in run_root.iterdir() if path.is_dir() and path.name not in ignored)


def _pipeline_log_tails(pipeline: dict[str, Any], max_lines: int = 40) -> list[dict[str, Any]]:
    tails: list[dict[str, Any]] = []
    for stage, item in (pipeline.get("stages") or {}).items():
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        log_path = details.get("log_path")
        if not log_path:
            continue
        lines = _tail_lines(Path(str(log_path)), max_lines=max_lines)
        if lines:
            tails.append({"stage": stage, "log_path": str(log_path), "lines": lines})
    return tails


def parse_pipeline_progress(lines: list[str]) -> dict[str, Any] | None:
    completed: int | None = None
    total: int | None = None
    for line in lines:
        progress_match = re.search(r"Progress:\s*(\d+)\s*/\s*(\d+)\s+crawled", line)
        if progress_match:
            completed = int(progress_match.group(1))
            total = int(progress_match.group(2))
            continue
        final_match = re.search(r"Crawled\s+(\d+)\s+successful pages from\s+(\d+)\s+URLs", line)
        if final_match:
            completed = int(final_match.group(2))
            total = int(final_match.group(2))
            continue
        discovered_match = re.search(r"Discovered\s+(\d+)\s+URLs", line)
        if discovered_match and total is None:
            total = int(discovered_match.group(1))
            completed = 0
    if total is None or total <= 0 or completed is None:
        return None
    bounded_completed = min(max(completed, 0), total)
    percent = round((bounded_completed / total) * 100, 1)
    return {
        "completed": bounded_completed,
        "total": total,
        "percent": percent,
        "label": f"{bounded_completed}/{total} pages",
    }


def _pipeline_progress(pipeline_log_tails: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    progress: dict[str, dict[str, Any]] = {}
    for item in pipeline_log_tails:
        parsed = parse_pipeline_progress([str(line) for line in item.get("lines", [])])
        if parsed:
            progress[str(item.get("stage") or "unknown")] = parsed
    return progress


def _current_stage(models: list[dict[str, Any]]) -> str:
    if not models:
        return "empty"
    stages = [model["summary"]["status"] for model in models]
    if all(stage == "complete" for stage in stages):
        return "complete"
    if any(stage == "complete_with_failures" for stage in stages) and all(
        bool((model.get("run_status") or {}).get("complete_outputs")) for model in models
    ):
        return "complete_with_model_warnings"
    if any(
        model["summary"]["tasks"].get("answer", {}).get("terminal_calls", 0) > 0
        and model["summary"]["missing"]["answer_rows"] > 0
        for model in models
    ):
        return "answer"
    if any(
        model["summary"]["tasks"].get("rerank", {}).get("terminal_calls", 0) > 0
        and model["summary"]["missing"]["retrieval_rows"] > 0
        for model in models
    ):
        return "rerank"
    for model in models:
        missing = model["summary"]["missing"]
        if missing["queries"] > 0:
            return "scenario_generation"
        if missing["retrieval_rows"] > 0:
            return "rerank"
        if missing["answer_rows"] > 0:
            return "answer"
    if any(stage == "likely_stalled" for stage in stages):
        return "stalled"
    return "merge_or_report"


def _build_health(pipeline: dict[str, Any], models: list[dict[str, Any]]) -> dict[str, Any]:
    status = "ok"
    issues: list[str] = []
    workers_completed_acceptably = bool(models) and all(
        str(model.get("exit_code") or "").strip() in {"0", ""}
        and str((model.get("summary") or {}).get("status") or "") in {"complete", "complete_with_failures"}
        and int(((model.get("summary") or {}).get("missing") or {}).get("retrieval_rows") or 0) == 0
        and int(((model.get("summary") or {}).get("missing") or {}).get("answer_rows") or 0) == 0
        for model in models
    )
    has_model_warnings = any(bool((model.get("run_status") or {}).get("warning")) for model in models)

    def bump(level: str) -> None:
        nonlocal status
        if level == "error":
            status = "error"
        elif level == "model_warning" and status != "error":
            status = "complete_with_model_warnings"
        elif level == "warning" and status == "ok":
            status = "warning"

    def add_api_failure_guidance(safe_name: str, summary: dict[str, Any]) -> None:
        failure_text = "\n".join(str(row.get("error") or "") for row in summary.get("failures") or [])
        lower = failure_text.lower()
        if "402" in failure_text or "payment required" in lower:
            issues.append(f"{safe_name}: Payment required detected; stop the run, top up API credit, then resume.")
        elif "429" in failure_text or "too many requests" in lower or "rate limit" in lower:
            issues.append(f"{safe_name}: Rate limit detected; wait or stop the run, then resume after backoff.")

    for stage, item in (pipeline.get("stages") or {}).items():
        if str(item.get("status") or "").lower() == "failed":
            if stage == "answer" and workers_completed_acceptably:
                bump("model_warning" if has_model_warnings else "warning")
                if has_model_warnings:
                    issues.append(
                        "Parent pipeline marked answer failed, but model outputs are complete; merge can continue with warnings."
                    )
                else:
                    issues.append(
                        "Parent pipeline marked answer failed, but all model workers completed cleanly; merge may have been skipped."
                    )
            else:
                bump("error")
                issues.append(f"Pipeline stage {stage} failed: {item.get('message') or 'no message'}")

    for model in models:
        safe_name = str(model.get("safe_name") or model.get("model_dir") or "unknown")
        exit_code = str(model.get("exit_code") or "").strip()
        summary = model.get("summary") or {}
        totals = summary.get("totals") or {}
        missing = summary.get("missing") or {}
        model_status = str(summary.get("status") or "")
        run_status = model.get("run_status") or {}
        complete_outputs = bool(run_status.get("complete_outputs"))

        if exit_code and exit_code != "0":
            if complete_outputs:
                bump("model_warning")
                issues.append(f"{safe_name} exited with code {exit_code}, but complete outputs are present.")
            else:
                bump("error")
                issues.append(f"{safe_name} exited with code {exit_code}.")
        if int(totals.get("failures") or 0) > 0:
            add_api_failure_guidance(safe_name, summary)
            if complete_outputs:
                bump("model_warning")
                messages = [str(item) for item in run_status.get("messages") or [] if str(item)]
                issues.extend(messages or [f"{safe_name} had {totals.get('failures')} API failures; interpret with caution."])
            else:
                bump("error")
                issues.append(f"{safe_name} has {totals.get('failures')} API failures.")
        if model_status == "likely_stalled":
            bump("warning")
            issues.append(f"{safe_name} is likely stalled.")

        missing_answers = int(missing.get("answer_rows") or 0)
        missing_retrieval = int(missing.get("retrieval_rows") or 0)
        if missing_answers > 0 and model_status not in {"empty", "complete"}:
            bump("warning")
            issues.append(f"{safe_name} has {missing_answers} missing answer rows.")
        if missing_retrieval > 0 and model_status not in {"empty", "complete"}:
            bump("warning")
            issues.append(f"{safe_name} has {missing_retrieval} missing retrieval rows.")

    return {"status": status, "issues": issues}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def summarize_parallel_run(run_root: Path | str, target_brand: str = "AlphaXXXX") -> dict[str, Any]:
    root = Path(run_root)
    pipeline = read_pipeline_status(root)
    pipeline_log_tails = _pipeline_log_tails(pipeline)
    models = []
    for model_dir in _model_dirs(root):
        summary = summarize_run(model_dir)
        exit_code = (
            (model_dir / "worker_exit_code.txt").read_text(encoding="utf-8").strip()
            if (model_dir / "worker_exit_code.txt").exists()
            else ""
        )
        models.append(
            {
                "model_dir": str(model_dir),
                "safe_name": model_dir.name,
                "summary": summary,
                "run_status": summarize_run_dir(model_dir, exit_code=exit_code),
                "log_tail": _tail_lines(model_dir / "worker.log"),
                "exit_code": exit_code,
            }
        )

    totals = {
        "queries": sum(int(model["summary"]["totals"]["queries"]) for model in models),
        "expected_api_calls": sum(int(model["summary"]["totals"]["expected_api_calls"]) for model in models),
        "terminal_calls": sum(int(model["summary"]["totals"]["terminal_calls"]) for model in models),
        "api_calls": sum(int(model["summary"]["totals"]["api_calls"]) for model in models),
        "cache_hits": sum(int(model["summary"]["totals"]["cache_hits"]) for model in models),
        "failures": sum(int(model["summary"]["totals"]["failures"]) for model in models),
    }
    totals["progress"] = (
        min(totals["terminal_calls"] / totals["expected_api_calls"], 1.0)
        if totals["expected_api_calls"]
        else 0.0
    )

    health = _build_health(pipeline, models)
    model_stage = _current_stage(models)
    current_stage = pipeline["current_stage"] or model_stage
    if health["status"] == "complete_with_model_warnings" and model_stage == "complete_with_model_warnings":
        current_stage = model_stage
    ops_summary = read_summary(root)
    if ops_summary:
        key_files = ops_summary.get("key_files")
        health = {
            "status": str(ops_summary.get("status") or health.get("status") or "unknown"),
            "issues": _strings(ops_summary.get("issues") or []),
            "recommended_actions": _strings(ops_summary.get("recommended_actions") or []),
            "source": "ops_summary",
            "key_files": key_files if isinstance(key_files, dict) else {},
        }

    return {
        "run_root": str(root),
        "current_stage": current_stage,
        "pipeline": pipeline,
        "pipeline_log_tails": pipeline_log_tails,
        "pipeline_progress": _pipeline_progress(pipeline_log_tails),
        "health": health,
        "totals": totals,
        "models": models,
        "progress_html": str(root / "progress.html") if (root / "progress.html").exists() else "",
        "report": summarize_latest_report(root, target_brand=target_brand).to_dict(),
    }
