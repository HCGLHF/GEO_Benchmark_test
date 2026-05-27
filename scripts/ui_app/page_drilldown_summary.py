from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.page_drilldown import build_owned_page_drilldown, load_owned_pages, read_retrieval_evidence
from scripts.ui_app.report_history import list_report_history


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _resolve_known_report_dir(project_root: Path, report_dir: str) -> Path:
    requested = Path(report_dir)
    if not requested.is_absolute():
        requested = project_root / requested
    requested = requested.resolve()
    runs_root = (project_root / "runs").resolve()
    try:
        requested.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError("report_dir must be under runs/") from exc
    known = {item.report_dir.resolve() for item in list_report_history(project_root, limit=500)}
    if requested not in known:
        raise ValueError("report_dir is not a known completed report")
    return requested


def summarize_report_page_drilldown(
    project_root: Path | str = Path("."),
    report_dir: str = "",
    target_brand: str = "AlphaXXXX",
    limit: int = 15,
) -> dict[str, Any]:
    root = Path(project_root)
    resolved = _resolve_known_report_dir(root, report_dir)
    top_pages = _read_csv_rows(resolved / "owned_top5_pages.csv")
    weak_pages = _read_csv_rows(resolved / "owned_weak_pages.csv")
    source = "csv"
    if not top_pages and not weak_pages:
        owned_pages = load_owned_pages(root / "data" / "processed" / "documents.jsonl", target_brand)
        drilldown = build_owned_page_drilldown(
            target_brand,
            read_retrieval_evidence(resolved / "retrieval_evidence_by_model.jsonl"),
            owned_pages=owned_pages,
            limit=limit,
        )
        top_pages = drilldown.top_pages
        weak_pages = drilldown.weak_pages
        source = "computed"
    return {
        "report_dir": str(resolved),
        "source": source,
        "top_pages": top_pages[:limit],
        "weak_pages": weak_pages[:limit],
    }
