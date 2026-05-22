from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read_brand_rows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / "brand_performance_by_model.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_true(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def summarize_target(run_dir: Path, target_brand: str) -> dict[str, Any]:
    rows = [
        row
        for row in read_brand_rows(run_dir)
        if row.get("brand") == target_brand or is_true(row.get("is_target", ""))
    ]
    query_count = sum(int(row.get("query_count") or 0) for row in rows)
    top5_count = sum(int(row.get("top5_count") or 0) for row in rows)
    mention_count = sum(int(row.get("model_mention_count") or 0) for row in rows)
    urls: list[str] = []
    for row in rows:
        try:
            urls.extend(str(item) for item in json.loads(row.get("top_urls_json") or "[]"))
        except json.JSONDecodeError:
            continue
    return {
        "run_dir": str(run_dir),
        "query_count": query_count,
        "top5_count": top5_count,
        "top5_share": top5_count / query_count if query_count else 0.0,
        "model_mention_count": mention_count,
        "model_mention_rate": mention_count / query_count if query_count else 0.0,
        "top_urls": sorted(set(urls)),
    }


def compare_runs(with_llms_dir: Path, without_llms_dir: Path, target_brand: str) -> dict[str, Any]:
    with_summary = summarize_target(with_llms_dir, target_brand)
    without_summary = summarize_target(without_llms_dir, target_brand)
    return {
        "target_brand": target_brand,
        "with_llms": with_summary,
        "without_llms": without_summary,
        "delta": {
            "top5_share": with_summary["top5_share"] - without_summary["top5_share"],
            "model_mention_rate": with_summary["model_mention_rate"] - without_summary["model_mention_rate"],
            "top5_count": with_summary["top5_count"] - without_summary["top5_count"],
            "model_mention_count": with_summary["model_mention_count"] - without_summary["model_mention_count"],
        },
    }


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def pp(value: float) -> str:
    return f"{value * 100:.1f} pp"


def render_url_list(urls: list[str]) -> str:
    if not urls:
        return "- None"
    return "\n".join(f"- {url}" for url in urls)


def render_markdown(result: dict[str, Any]) -> str:
    with_summary = result["with_llms"]
    without_summary = result["without_llms"]
    delta = result["delta"]
    return f"""# llms.txt Lift Report: {result['target_brand']}

## Summary

| Metric | With llms.txt | Without llms.txt | Lift |
| --- | ---: | ---: | ---: |
| Retrieval Top5 Share | {pct(with_summary['top5_share'])} | {pct(without_summary['top5_share'])} | {pp(delta['top5_share'])} |
| Model Mention Rate | {pct(with_summary['model_mention_rate'])} | {pct(without_summary['model_mention_rate'])} | {pp(delta['model_mention_rate'])} |
| Top5 Count | {with_summary['top5_count']} | {without_summary['top5_count']} | {delta['top5_count']} |
| Mention Count | {with_summary['model_mention_count']} | {without_summary['model_mention_count']} | {delta['model_mention_count']} |

## With llms.txt Top AlphaXXXX URLs

{render_url_list(with_summary['top_urls'])}

## Without llms.txt Top AlphaXXXX URLs

{render_url_list(without_summary['top_urls'])}

## Interpretation

- Positive lift means `llms.txt` is helping route model retrieval or answers toward AlphaXXXX.
- If the without-llms score is also rising, the business pages are becoming stronger evidence pages.
- If with-llms rises but without-llms stays low, `llms.txt` is acting as the main router and page-level content still needs strengthening.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare with-llms and without-llms merged full API runs.")
    parser.add_argument("--with-llms-run", required=True)
    parser.add_argument("--without-llms-run", required=True)
    parser.add_argument("--target-brand", default="AlphaXXXX")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = compare_runs(Path(args.with_llms_run), Path(args.without_llms_run), args.target_brand)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(result), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
