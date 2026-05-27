from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_eval.io import load_config


FIELDS = [
    "brand",
    "is_target",
    "query_count",
    "top1_count",
    "top5_count",
    "top10_count",
    "top10_slot_count",
    "top5_query_share",
    "top10_query_share",
    "best_rank",
    "average_best_rank",
    "model_mention_count",
    "model_mention_rate",
    "unique_url_count",
    "top_urls_json",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pct(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator if denominator else 0.0):.1%}"


def load_retrieved_rankings(run_dir: Path) -> tuple[int, dict[str, list[int]], dict[str, Counter[str]]]:
    evidence_rows = read_jsonl(run_dir / "retrieval_evidence.jsonl")
    ranks_by_brand: dict[str, list[int]] = defaultdict(list)
    urls_by_brand: dict[str, Counter[str]] = defaultdict(Counter)

    for row in evidence_rows:
        seen_urls_for_query: set[tuple[str, str]] = set()
        for rank, chunk in enumerate(row.get("retrieved_chunks", [])[:10], start=1):
            brand = str(chunk.get("brand") or "Unknown").strip() or "Unknown"
            url = str(chunk.get("url") or "").strip()
            ranks_by_brand[brand].append(rank)
            if url and (brand, url) not in seen_urls_for_query:
                urls_by_brand[brand][url] += 1
                seen_urls_for_query.add((brand, url))

    return len(evidence_rows), ranks_by_brand, urls_by_brand


def load_model_mention_counts(run_dir: Path, brands: set[str]) -> tuple[int, Counter[str]]:
    responses = [row for row in read_jsonl(run_dir / "model_responses.jsonl") if not row.get("error")]
    counts: Counter[str] = Counter()
    for response in responses:
        answer = str(response.get("raw_answer") or "").lower()
        for brand in brands:
            if brand and brand.lower() in answer:
                counts[brand] += 1
    return len(responses), counts


def summarize_brand(
    brand: str,
    target_brand: str,
    query_count: int,
    response_count: int,
    ranks: list[int],
    urls: Counter[str],
    model_mentions: int,
) -> dict[str, Any]:
    per_query_top1 = sum(1 for rank in ranks if rank == 1)
    top5_hits = sum(1 for rank in ranks if rank <= 5)
    top10_hits = sum(1 for rank in ranks if rank <= 10)
    query_top5_count = min(top5_hits, query_count)
    query_top10_count = min(top10_hits, query_count)
    best_rank = min(ranks) if ranks else ""
    average_best_rank = f"{(sum(ranks) / len(ranks)):.2f}" if ranks else ""
    return {
        "brand": brand,
        "is_target": str(brand == target_brand),
        "query_count": query_count,
        "top1_count": per_query_top1,
        "top5_count": query_top5_count,
        "top10_count": query_top10_count,
        "top10_slot_count": len(ranks),
        "top5_query_share": pct(query_top5_count, query_count),
        "top10_query_share": pct(query_top10_count, query_count),
        "best_rank": best_rank,
        "average_best_rank": average_best_rank,
        "model_mention_count": model_mentions,
        "model_mention_rate": pct(model_mentions, response_count),
        "unique_url_count": len(urls),
        "top_urls_json": json.dumps([url for url, _count in urls.most_common(5)], ensure_ascii=False),
    }


def build_brand_rows(run_dir: Path, target_brand: str, configured_brands: list[str]) -> list[dict[str, Any]]:
    query_count, ranks_by_brand, urls_by_brand = load_retrieved_rankings(run_dir)
    brands = {target_brand, *configured_brands, *ranks_by_brand.keys()}
    response_count, mention_counts = load_model_mention_counts(run_dir, brands)
    rows = [
        summarize_brand(
            brand=brand,
            target_brand=target_brand,
            query_count=query_count,
            response_count=response_count,
            ranks=ranks_by_brand.get(brand, []),
            urls=urls_by_brand.get(brand, Counter()),
            model_mentions=mention_counts.get(brand, 0),
        )
        for brand in sorted(brands, key=lambda item: (item != target_brand, item.lower()))
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["is_target"] != "True",
            -int(row["top5_count"]),
            -int(row["top10_slot_count"]),
            str(row["brand"]).lower(),
        ),
    )


def write_outputs(rows: list[dict[str, Any]], csv_path: Path, markdown_path: Path, target_brand: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    target = next((row for row in rows if row["brand"] == target_brand), None)
    leaders = [row for row in rows if row["brand"] != target_brand][:10]
    lines = [
        f"# Brand Performance Comparison: {target_brand}",
        "",
        "## Target Snapshot",
        "",
    ]
    if target:
        lines.extend(
            [
                f"- Top5 query share: {target['top5_query_share']}",
                f"- Top10 query share: {target['top10_query_share']}",
                f"- Best rank: {target['best_rank'] or 'not ranked'}",
                f"- Model mention rate: {target['model_mention_rate']}",
                f"- Unique retrieved URLs: {target['unique_url_count']}",
            ]
        )
    else:
        lines.append("- Target brand was not present in the comparison rows.")
    lines.extend(["", "## Competitor Leaders", "", "| Brand | Top5 Share | Top10 Slots | Best Rank | Model Mention | URLs |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in leaders:
        lines.append(
            f"| {row['brand']} | {row['top5_query_share']} | {row['top10_slot_count']} | "
            f"{row['best_rank'] or 'not ranked'} | {row['model_mention_rate']} | {row['unique_url_count']} |"
        )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare target brand performance against retrieved competitors for one run.")
    parser.add_argument("--config", default="config/geo_evaluator.yaml")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    campaign = config.get("campaign", {})
    target_brand = str(campaign.get("target_brand", ""))
    configured_brands = [str(item) for item in campaign.get("competitors", [])]
    run_dir = Path(args.run_dir or config.get("run", {}).get("output_dir", "runs/geo_evaluator"))
    output = Path(args.output or run_dir / "brand_performance.csv")
    markdown = Path(args.markdown or run_dir / "brand_performance.md")

    rows = build_brand_rows(run_dir, target_brand, configured_brands)
    write_outputs(rows, output, markdown, target_brand)
    print(f"Wrote brand performance comparison to {output} and {markdown}")


if __name__ == "__main__":
    main()
