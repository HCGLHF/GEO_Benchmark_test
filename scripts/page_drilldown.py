from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PAGE_DRILLDOWN_FIELDS = [
    "url",
    "title",
    "top5_hit_count",
    "top5_query_count",
    "best_rank",
    "model_count",
    "persona_count",
    "journey_stage_count",
    "optimization_hint",
]


@dataclass(frozen=True)
class OwnedPageDrilldown:
    top_pages: list[dict[str, Any]]
    weak_pages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"top_pages": self.top_pages, "weak_pages": self.weak_pages}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_owned_pages(documents_path: Path | str, target_brand: str) -> list[dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(Path(documents_path)):
        if str(row.get("brand") or "").lower() != target_brand.lower():
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        pages[url] = {
            "url": url,
            "title": str(row.get("title") or url),
            "content_length": len(str(row.get("content") or "")),
        }
    return sorted(pages.values(), key=lambda item: item["url"])


def read_retrieval_evidence(path: Path | str) -> list[dict[str, Any]]:
    return _read_jsonl(Path(path))


def _hint(row: dict[str, Any]) -> str:
    if int(row.get("top5_query_count") or 0) == 0:
        return "No Top5 retrieval in this run; strengthen intent coverage, title/H1 clarity, answer-style sections, and internal links from llms.txt."
    if int(row.get("model_count") or 0) <= 1:
        return "Retrieved by only one model; add model-friendly summaries, examples, comparison language, and clearer evidence/citations."
    return "Retrieved but still fragile; expand query-specific sections and make the page a stronger canonical answer for this intent."


def _blank_page(url: str, title: str = "", content_length: int = 0) -> dict[str, Any]:
    return {
        "url": url,
        "title": title or url,
        "top5_hit_count": 0,
        "top5_query_count": 0,
        "best_rank": "",
        "model_count": 0,
        "persona_count": 0,
        "journey_stage_count": 0,
        "content_length": content_length,
    }


def _markdown_cell(value: Any, max_len: int = 160) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = text.replace("|", "\\|")
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def build_owned_page_drilldown(
    target_brand: str,
    retrieval_evidence: list[dict[str, Any]],
    owned_pages: list[dict[str, Any]] | None = None,
    limit: int = 15,
) -> OwnedPageDrilldown:
    pages: dict[str, dict[str, Any]] = {}
    query_hits: dict[str, set[str]] = defaultdict(set)
    model_hits: dict[str, set[str]] = defaultdict(set)
    persona_hits: dict[str, set[str]] = defaultdict(set)
    stage_hits: dict[str, set[str]] = defaultdict(set)

    for page in owned_pages or []:
        url = str(page.get("url") or "").strip()
        if not url:
            continue
        pages[url] = _blank_page(url, str(page.get("title") or url), int(page.get("content_length") or 0))

    for evidence in retrieval_evidence:
        query_id = str(evidence.get("query_id") or "")
        model = str(evidence.get("model") or "")
        persona = str(evidence.get("persona") or "")
        stage = str(evidence.get("journey_stage") or "")
        chunks = evidence.get("retrieved_chunks") if isinstance(evidence.get("retrieved_chunks"), list) else []
        for rank, chunk in enumerate(chunks[:5], start=1):
            if str(chunk.get("brand") or "").lower() != target_brand.lower():
                continue
            url = str(chunk.get("url") or "").strip()
            if not url:
                continue
            row = pages.setdefault(url, _blank_page(url, str(chunk.get("title") or url)))
            if not row.get("title") or row.get("title") == url:
                row["title"] = str(chunk.get("title") or url)
            row["top5_hit_count"] = int(row.get("top5_hit_count") or 0) + 1
            best_rank = row.get("best_rank")
            row["best_rank"] = rank if not best_rank else min(int(best_rank), rank)
            if query_id:
                query_hits[url].add(query_id)
            if model:
                model_hits[url].add(model)
            if persona:
                persona_hits[url].add(persona)
            if stage:
                stage_hits[url].add(stage)

    for url, row in pages.items():
        row["top5_query_count"] = len(query_hits[url])
        row["model_count"] = len(model_hits[url])
        row["persona_count"] = len(persona_hits[url])
        row["journey_stage_count"] = len(stage_hits[url])
        row["optimization_hint"] = _hint(row)

    all_rows = list(pages.values())
    top_pages = sorted(
        [row for row in all_rows if int(row.get("top5_query_count") or 0) > 0],
        key=lambda row: (
            -int(row.get("top5_query_count") or 0),
            -int(row.get("top5_hit_count") or 0),
            int(row.get("best_rank") or sys.maxsize),
            str(row.get("url") or ""),
        ),
    )[:limit]
    weak_pages = sorted(
        all_rows,
        key=lambda row: (
            int(row.get("top5_query_count") or 0),
            int(row.get("model_count") or 0),
            int(row.get("best_rank") or sys.maxsize),
            str(row.get("url") or ""),
        ),
    )[:limit]
    return OwnedPageDrilldown(top_pages=top_pages, weak_pages=weak_pages)


def write_page_drilldown_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAGE_DRILLDOWN_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_owned_page_sections(target_brand: str, drilldown: OwnedPageDrilldown, limit: int = 10) -> str:
    lines = [
        f"## {target_brand} Top5 Retrieved Pages",
        "",
        "| URL | Title | Top5 Queries | Top5 Hits | Best Rank | Models |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    if drilldown.top_pages:
        for row in drilldown.top_pages[:limit]:
            lines.append(
                f"| {row['url']} | {_markdown_cell(row.get('title', ''))} | {row['top5_query_count']} | "
                f"{row['top5_hit_count']} | {row.get('best_rank') or 'not ranked'} | {row['model_count']} |"
            )
    else:
        lines.append(f"| No {target_brand} pages entered Top5 in this run. |  |  |  |  |  |")

    lines.extend(
        [
            "",
            f"## {target_brand} Weak Pages To Optimize",
            "",
            "| URL | Title | Top5 Queries | Models | Suggested Fix |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    if drilldown.weak_pages:
        for row in drilldown.weak_pages[:limit]:
            lines.append(
                f"| {row['url']} | {_markdown_cell(row.get('title', ''))} | {row['top5_query_count']} | "
                f"{row['model_count']} | {row['optimization_hint']} |"
            )
    else:
        lines.append("| No owned pages were available for weak-page analysis. |  |  |  |  |")
    return "\n".join(lines) + "\n"
