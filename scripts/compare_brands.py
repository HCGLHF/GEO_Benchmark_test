from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


KEYWORDS = [
    "generative engine optimization",
    "generative engine optimisation",
    "geo",
    "ai search",
    "answer engine",
    "llm",
    "llms.txt",
    "citation",
    "brand mention",
    "visibility",
    "schema",
    "structured data",
    "faq",
    "pricing",
]


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def count_keyword(text: str, keyword: str) -> int:
    if keyword == "geo":
        pattern = r"\bgeo\b"
    elif keyword == "llm":
        pattern = r"\bllms?\b"
    else:
        pattern = re.escape(keyword)
    return len(re.findall(pattern, text, flags=re.I))


def keyword_coverage(keyword_counts: dict[str, int]) -> float:
    return sum(1 for keyword in KEYWORDS if keyword_counts.get(keyword, 0) > 0) / len(KEYWORDS)


def compute_brand_stats(documents: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(
        lambda: {
            "pages": 0,
            "total_chars": 0,
            "urls": set(),
            "keyword_counts": {keyword: 0 for keyword in KEYWORDS},
        }
    )
    for doc in documents:
        brand = doc.get("brand") or "Unknown"
        content = doc.get("content") or ""
        stats[brand]["pages"] += 1
        stats[brand]["total_chars"] += len(content)
        stats[brand]["urls"].add(doc.get("url", ""))
        for keyword in KEYWORDS:
            stats[brand]["keyword_counts"][keyword] += count_keyword(content, keyword)

    normalized: dict[str, dict] = {}
    for brand, values in stats.items():
        pages = int(values["pages"])
        total_chars = int(values["total_chars"])
        keyword_counts = values["keyword_counts"]
        normalized[brand] = {
            "pages": pages,
            "total_chars": total_chars,
            "avg_chars_per_page": round(total_chars / pages) if pages else 0,
            "unique_urls": len(values["urls"]),
            "keyword_counts": keyword_counts,
            "keyword_coverage": keyword_coverage(keyword_counts),
        }
    return normalized


def top_missing_keywords(target: dict, competitors: dict[str, dict]) -> list[tuple[str, int, int]]:
    missing: list[tuple[str, int, int]] = []
    target_counts = target["keyword_counts"]
    for keyword in KEYWORDS:
        competitor_total = sum(stats["keyword_counts"].get(keyword, 0) for stats in competitors.values())
        if target_counts.get(keyword, 0) == 0 and competitor_total > 0:
            competitor_brands = sum(
                1 for stats in competitors.values() if stats["keyword_counts"].get(keyword, 0) > 0
            )
            missing.append((keyword, competitor_total, competitor_brands))
    return sorted(missing, key=lambda item: (item[2], item[1]), reverse=True)


def format_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for index, row in enumerate(rows):
        lines.append("| " + " | ".join(str(value).ljust(widths[col]) for col, value in enumerate(row)) + " |")
        if index == 0:
            lines.append("| " + " | ".join("-" * width for width in widths) + " |")
    return lines


def generate_comparison_report(documents: list[dict], target_brand: str) -> str:
    stats = compute_brand_stats(documents)
    target = stats.get(target_brand)
    if not target:
        raise ValueError(f"Target brand not found: {target_brand}")

    competitors = {brand: value for brand, value in stats.items() if brand != target_brand and brand != "Unknown"}
    ranked = sorted(stats.items(), key=lambda item: (item[1]["pages"], item[1]["total_chars"]), reverse=True)

    lines = [f"# Brand Comparison: {target_brand}", ""]
    lines.extend(
        [
            "## Target Snapshot",
            "",
            f"- Pages: {target['pages']}",
            f"- Total characters: {target['total_chars']:,}",
            f"- Average characters per page: {target['avg_chars_per_page']:,}",
            f"- Keyword coverage: {target['keyword_coverage']:.1%}",
            "",
            "## Brand Scale",
            "",
        ]
    )

    table = [["Brand", "Pages", "Chars", "Avg chars/page", "Keyword coverage"]]
    for brand, values in ranked:
        table.append(
            [
                brand,
                str(values["pages"]),
                f"{values['total_chars']:,}",
                f"{values['avg_chars_per_page']:,}",
                f"{values['keyword_coverage']:.0%}",
            ]
        )
    lines.extend(format_table(table))

    lines.extend(["", "## Keyword Coverage", ""])
    keyword_table = [["Keyword", target_brand, "Competitor brands using it", "Competitor total mentions"]]
    for keyword in KEYWORDS:
        competitor_brands = sum(1 for values in competitors.values() if values["keyword_counts"].get(keyword, 0) > 0)
        competitor_total = sum(values["keyword_counts"].get(keyword, 0) for values in competitors.values())
        keyword_table.append(
            [
                keyword,
                str(target["keyword_counts"].get(keyword, 0)),
                str(competitor_brands),
                str(competitor_total),
            ]
        )
    lines.extend(format_table(keyword_table))

    lines.extend(["", "## Content Gaps", ""])
    missing = top_missing_keywords(target, competitors)
    if missing:
        for keyword, total, brands in missing:
            lines.append(f"- `{keyword}`: absent from {target_brand}, present in {brands} other brands ({total} mentions).")
    else:
        lines.append("- No tracked keyword is completely absent from the target site.")

    lines.extend(["", "## Interpretation", ""])
    median_pages = sorted(value["pages"] for value in competitors.values())[len(competitors) // 2] if competitors else 0
    if target["pages"] < median_pages:
        lines.append(
            f"- {target_brand} has fewer indexed pages than the median competitor in this resource pool "
            f"({target['pages']} vs {median_pages})."
        )
    else:
        lines.append(f"- {target_brand} has page depth near or above the median competitor in this resource pool.")
    lines.append(
        "- This is a corpus comparison, not a live ranking audit. The next step is to run a larger query set "
        "against retrieval and answer-generation metrics."
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a target brand against the resource library.")
    parser.add_argument("--documents", default="data/processed/documents.jsonl")
    parser.add_argument("--target-brand", default="AlphaXXXX")
    parser.add_argument("--output", default="reports/brand_comparison_alpha.md")
    args = parser.parse_args()

    report = generate_comparison_report(read_jsonl(Path(args.documents)), args.target_brand)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"Wrote brand comparison report to {args.output}")


if __name__ == "__main__":
    main()
