from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.watch_full_api_run import summarize_run


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _status_label(status: str) -> str:
    labels = {
        "empty": "Waiting",
        "active": "Running",
        "likely_stalled": "Stalled",
        "complete": "Complete",
        "complete_with_failures": "Complete with failures",
    }
    return labels.get(status, status.replace("_", " ").title())


def _progress_bar(progress: float) -> str:
    width = max(0.0, min(progress, 1.0)) * 100
    return (
        '<div class="bar" aria-label="progress">'
        f'<span style="width:{width:.1f}%"></span>'
        "</div>"
    )


def _task_rows(summary: dict[str, Any]) -> str:
    rows: list[str] = []
    for task_type, row in summary["tasks"].items():
        expected = summary["expected_by_task"].get(task_type, 0)
        rows.append(
            "<tr>"
            f"<td>{_escape(task_type)}</td>"
            f"<td>{_escape(row['terminal_calls'])}/{_escape(expected)}</td>"
            f"<td>{_escape(row['api_calls'])}</td>"
            f"<td>{_escape(row['cache_hits'])}</td>"
            f"<td>{_escape(row['failures'])}</td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="5" class="muted">No task attempts yet</td></tr>'
    return "".join(rows)


def _failure_items(summary: dict[str, Any]) -> str:
    if not summary["failures"]:
        return '<li class="muted">No observed failures</li>'
    return "".join(
        "<li>"
        f"<strong>{_escape(failure['task_type'])}</strong> "
        f"{_escape(failure['query_id'])}: {_escape(failure['error'])}"
        "</li>"
        for failure in summary["failures"]
    )


def _run_card(summary: dict[str, Any]) -> str:
    name = Path(summary["run_dir"]).name
    totals = summary["totals"]
    outputs = summary["outputs"]
    missing = summary["missing"]
    timing = summary["timing"]
    status = str(summary["status"])
    return f"""
      <section class="model-card status-{_escape(status)}">
        <div class="model-head">
          <div>
            <h2>{_escape(name)}</h2>
            <p>{_escape(summary["run_dir"])}</p>
          </div>
          <span class="status-pill">{_escape(_status_label(status))}</span>
        </div>
        <div class="progress-line">
          {_progress_bar(float(totals["progress"]))}
          <strong>{_escape(_pct(float(totals["progress"])))}</strong>
        </div>
        <div class="metric-grid">
          <div><span>Terminal</span><strong>{_escape(totals["terminal_calls"])}/{_escape(totals["expected_api_calls"])}</strong></div>
          <div><span>API calls</span><strong>{_escape(totals["api_calls"])}</strong></div>
          <div><span>Failures</span><strong>{_escape(totals["failures"])}</strong></div>
          <div><span>Queries</span><strong>{_escape(totals["queries"])}</strong></div>
          <div><span>Retrieval rows</span><strong>{_escape(outputs["retrieval_rows"])}</strong></div>
          <div><span>Answer rows</span><strong>{_escape(outputs["answer_rows"])}</strong></div>
        </div>
        <div class="missing">Missing retrieval {missing["retrieval_rows"]}, answers {missing["answer_rows"]}, terminal calls {missing["terminal_calls"]}</div>
        <table>
          <thead><tr><th>Task</th><th>Done</th><th>API</th><th>Cache</th><th>Fail</th></tr></thead>
          <tbody>{_task_rows(summary)}</tbody>
        </table>
        <div class="foot">
          <span>Last activity: {_escape(timing["last_activity_at"] or "unknown")}</span>
          <span>Idle: {_escape(timing["idle_seconds"])}</span>
        </div>
        <details>
          <summary>Failure samples</summary>
          <ul>{_failure_items(summary)}</ul>
        </details>
      </section>
    """


def _overall_summary(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(int(item["totals"]["expected_api_calls"]) for item in summaries)
    terminal = sum(int(item["totals"]["terminal_calls"]) for item in summaries)
    api_calls = sum(int(item["totals"]["api_calls"]) for item in summaries)
    failures = sum(int(item["totals"]["failures"]) for item in summaries)
    retrieval_missing = sum(int(item["missing"]["retrieval_rows"]) for item in summaries)
    answer_missing = sum(int(item["missing"]["answer_rows"]) for item in summaries)
    progress = terminal / expected if expected else 0.0
    return {
        "expected": expected,
        "terminal": terminal,
        "api_calls": api_calls,
        "failures": failures,
        "retrieval_missing": retrieval_missing,
        "answer_missing": answer_missing,
        "progress": progress,
    }


def render_progress_html(run_dirs: list[Path], title: str = "Full API Progress") -> str:
    summaries = [summarize_run(path) for path in run_dirs]
    overall = _overall_summary(summaries)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cards = "\n".join(_run_card(summary) for summary in summaries)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #11110f;
      --panel: #1b1b17;
      --line: #34342d;
      --text: #f1efdf;
      --muted: #aaa68f;
      --accent: #d6ff5f;
      --warn: #ffca5f;
      --bad: #ff6f5f;
      --good: #79e68b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Aptos", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 32px 20px 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 24px; }}
    h1 {{ margin: 0; font-size: 34px; font-weight: 700; }}
    .subtle {{ color: var(--muted); margin-top: 6px; }}
    .overall {{
      border: 1px solid var(--line);
      background: #171713;
      padding: 18px;
      min-width: 320px;
    }}
    .bar {{ height: 10px; background: #2b2b25; overflow: hidden; border: 1px solid var(--line); }}
    .bar span {{ display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--good)); }}
    .overall .bar {{ margin-top: 10px; }}
    .summary-grid, .metric-grid {{ display: grid; gap: 10px; }}
    .summary-grid {{ grid-template-columns: repeat(3, 1fr); margin-top: 14px; }}
    .metric-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 18px 0; }}
    .summary-grid div, .metric-grid div {{ border-top: 1px solid var(--line); padding-top: 10px; }}
    span {{ color: var(--muted); font-size: 12px; display: block; }}
    strong {{ font-size: 18px; }}
    .runs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }}
    .model-card {{ border: 1px solid var(--line); background: var(--panel); padding: 18px; }}
    .model-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: start; }}
    h2 {{ margin: 0; font-size: 19px; }}
    h2 + p {{ margin: 5px 0 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .status-pill {{ border: 1px solid var(--line); padding: 6px 9px; color: var(--text); white-space: nowrap; }}
    .status-complete .status-pill {{ border-color: var(--good); color: var(--good); }}
    .status-complete_with_failures .status-pill, .status-likely_stalled .status-pill {{ border-color: var(--warn); color: var(--warn); }}
    .progress-line {{ display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px; margin-top: 18px; }}
    .missing {{ color: var(--muted); border: 1px solid var(--line); padding: 9px; margin-bottom: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 8px 6px; }}
    th {{ color: var(--muted); font-weight: 500; }}
    .foot {{ display: flex; justify-content: space-between; gap: 10px; margin-top: 12px; }}
    details {{ margin-top: 12px; }}
    summary {{ cursor: pointer; color: var(--accent); }}
    li {{ margin: 8px 0; overflow-wrap: anywhere; }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .overall {{ min-width: 0; margin-top: 18px; }}
      .runs {{ grid-template-columns: 1fr; }}
      .summary-grid, .metric-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{_escape(title)}</h1>
        <div class="subtle">Generated {generated_at}. Auto-refreshes every 30 seconds.</div>
      </div>
      <section class="overall">
        <div class="progress-line">
          {_progress_bar(float(overall["progress"]))}
          <strong>{_escape(_pct(float(overall["progress"])))}</strong>
        </div>
        <div class="summary-grid">
          <div><span>Terminal</span><strong>{overall["terminal"]}/{overall["expected"]}</strong></div>
          <div><span>API calls</span><strong>{overall["api_calls"]}</strong></div>
          <div><span>Failures</span><strong>{overall["failures"]}</strong></div>
          <div><span>Missing retrieval</span><strong>{overall["retrieval_missing"]}</strong></div>
          <div><span>Missing answers</span><strong>{overall["answer_missing"]}</strong></div>
        </div>
      </section>
    </header>
    <section class="runs">
      {cards}
    </section>
  </main>
</body>
</html>
"""


def write_progress_html(run_dirs: list[Path], output: Path, title: str = "Full API Progress") -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_progress_html(run_dirs, title=title), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a static HTML dashboard for full API run progress.")
    parser.add_argument("--run-dirs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="Full API Progress")
    args = parser.parse_args()

    write_progress_html([Path(item) for item in args.run_dirs], Path(args.output), title=args.title)
    print(args.output)


if __name__ == "__main__":
    main()
