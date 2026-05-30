from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def set_large_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    set_large_csv_field_limit()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rate(rows: list[dict[str, str]], field: str) -> float:
    if not rows:
        return 0.0
    return sum(str(row.get(field, "")).lower() == "true" for row in rows) / len(rows)


def generate_report(retrieval_rows: list[dict[str, str]], generation_rows: list[dict[str, str]]) -> str:
    lines = ["# GEO Report", ""]
    lines.extend(
        [
            "## Retrieval Performance",
            "",
            f"- Queries evaluated: {len(retrieval_rows)}",
            f"- Recall@3: {rate(retrieval_rows, 'own_brand_in_top_3'):.1%}",
            f"- Recall@5: {rate(retrieval_rows, 'own_brand_in_top_5'):.1%}",
            f"- Recall@10: {rate(retrieval_rows, 'own_brand_in_top_10'):.1%}",
            f"- Competitor Win Rate: {rate(retrieval_rows, 'competitor_above_owned'):.1%}",
            "",
            "## Weak Queries",
            "",
        ]
    )
    weak = [row for row in retrieval_rows if str(row.get("own_brand_in_top_10", "")).lower() != "true"]
    if weak:
        for row in weak[:20]:
            lines.append(f"- `{row.get('query_id')}` {row.get('query')}")
    else:
        lines.append("- No weak retrieval queries found.")

    lines.extend(["", "## Generation Performance", ""])
    if generation_rows:
        avg_coverage = sum(
            int(row.get("answer_coverage_score") or 0) for row in generation_rows
        ) / len(generation_rows)
        lines.extend(
            [
                f"- Answers evaluated: {len(generation_rows)}",
                f"- Brand Mention Rate: {rate(generation_rows, 'brand_mentioned'):.1%}",
                f"- Citation Rate: {rate(generation_rows, 'cited_own_url'):.1%}",
                f"- Recommendation Rate: {rate(generation_rows, 'recommended_own_brand'):.1%}",
                f"- Average Coverage Score: {avg_coverage:.2f}",
            ]
        )
    else:
        lines.append("- Generation evaluation has not been run.")

    lines.extend(["", "## Pages To Optimize First", ""])
    urls: dict[str, int] = {}
    for row in weak:
        for url in row.get("matched_urls_json", "").strip("[]").split(","):
            clean = url.strip().strip('"')
            if clean:
                urls[clean] = urls.get(clean, 0) + 1
    if urls:
        for url, count in sorted(urls.items(), key=lambda item: item[1], reverse=True)[:20]:
            lines.append(f"- {url} ({count} weak-query matches)")
    else:
        lines.append("- No page optimization candidates found from current results.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GEO benchmark Markdown report.")
    parser.add_argument("--retrieval-results", default="data/eval/retrieval_results.csv")
    parser.add_argument("--generation-results", default="data/eval/generation_results.csv")
    parser.add_argument("--output", default="reports/geo_report.md")
    args = parser.parse_args()

    report = generate_report(
        load_csv(Path(args.retrieval_results)), load_csv(Path(args.generation_results))
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"Wrote report to {args.output}")


if __name__ == "__main__":
    main()
