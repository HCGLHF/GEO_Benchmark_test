from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.ui_app.report_summary import (
    BrandMetric,
    canonical_report_dirs,
    report_sort_key,
    report_updated_at_iso,
    summarize_report_dir,
)


@dataclass(frozen=True)
class ReportHistoryItem:
    run_root: Path
    report_dir: Path
    report_path: Path
    updated_at: str
    query_count: int
    answer_count: int
    target_top5_share: float | None
    target_model_mention_rate: float | None
    target_rank_by_top5: int | None
    brands_above_target: list[BrandMetric]
    models: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["run_root"] = str(self.run_root)
        payload["report_dir"] = str(self.report_dir)
        payload["report_path"] = str(self.report_path)
        return payload


def _report_candidates(project_root: Path) -> list[Path]:
    runs_dir = project_root / "runs"
    if not runs_dir.exists():
        return []
    return [
        path
        for path in runs_dir.rglob("competitive_gap_report.md")
        if path.parent.name.lower().startswith("merged")
    ]


def _model_names(summary: Any) -> list[str]:
    names = [str(item.model) for item in summary.model_breakdowns if str(item.model).strip()]
    if names:
        return sorted(set(names))
    brand_file = Path(summary.report_dir or "") / "brand_performance_by_model.csv"
    if not brand_file.exists():
        return []
    import csv

    models: set[str] = set()
    with brand_file.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            model = str(row.get("model") or "").strip()
            if model:
                models.add(model)
    return sorted(models)


def list_report_history(
    project_root: Path | str = Path("."),
    target_brand: str = "AlphaXXXX",
    limit: int = 20,
) -> list[ReportHistoryItem]:
    root = Path(project_root)
    items: list[ReportHistoryItem] = []
    report_dirs = canonical_report_dirs([report_path.parent for report_path in _report_candidates(root)])
    for report_dir in report_dirs:
        report_path = report_dir / "competitive_gap_report.md"
        summary = summarize_report_dir(report_dir, target_brand=target_brand)
        items.append(
            ReportHistoryItem(
                run_root=report_dir.parent,
                report_dir=report_dir,
                report_path=report_path,
                updated_at=report_updated_at_iso(report_dir, report_path),
                query_count=summary.query_count,
                answer_count=summary.answer_count,
                target_top5_share=summary.target_top5_share,
                target_model_mention_rate=summary.target_model_mention_rate,
                target_rank_by_top5=summary.target_rank_by_top5,
                brands_above_target=summary.brands_above_target,
                models=_model_names(summary),
            )
        )
    items.sort(key=lambda item: report_sort_key(item.report_dir, item.report_path), reverse=True)
    return items[:limit]


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


def read_report_preview(
    project_root: Path | str = Path("."),
    report_dir: str = "",
    max_chars: int = 60_000,
) -> dict[str, Any]:
    root = Path(project_root)
    resolved = _resolve_known_report_dir(root, report_dir)
    report_path = resolved / "competitive_gap_report.md"
    content = report_path.read_text(encoding="utf-8", errors="replace")
    return {
        "report_dir": str(resolved),
        "report_path": str(report_path),
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }
