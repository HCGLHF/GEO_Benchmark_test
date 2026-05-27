from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrandMetric:
    brand: str
    top5_share: float
    model_mention_rate: float
    query_count: int
    top5_count: int


@dataclass(frozen=True)
class ModelBreakdown:
    model: str
    query_count: int
    target_top5_share: float
    leading_winner: str
    winner_count: int


@dataclass(frozen=True)
class LatestReportSummary:
    report_dir: Path | None
    query_count: int
    answer_count: int
    target_top5_share: float | None
    target_model_mention_rate: float | None
    target_rank_by_top5: int | None
    brands_above_target: list[BrandMetric]
    top_brands: list[BrandMetric]
    model_breakdowns: list[ModelBreakdown]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["report_dir"] = str(self.report_dir) if self.report_dir else None
        return payload


def _percent(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _int(value: str | int | None) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def _latest_merged_dir(root: Path) -> Path | None:
    runs_dir = root / "runs" if (root / "runs").exists() else root
    candidates = [
        path
        for path in runs_dir.rglob("brand_performance_by_model.csv")
        if path.parent.name.lower().startswith("merged")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def _read_manifest_counts(report_dir: Path) -> tuple[int, int]:
    manifest_path = report_dir / "merge_manifest.json"
    if not manifest_path.exists():
        return 0, 0
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0, 0
    result = data.get("result", {}) if isinstance(data.get("result"), dict) else {}
    return _int(result.get("query_rows")), _int(result.get("answer_rows"))


def _brand_metrics(report_dir: Path) -> list[BrandMetric]:
    path = report_dir / "brand_performance_by_model.csv"
    if not path.exists():
        return []
    grouped: dict[str, dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            brand = str(row.get("brand") or "").strip()
            if not brand:
                continue
            current = grouped.setdefault(brand, {"query_count": 0, "top5_count": 0, "mention_count": 0})
            query_count = _int(row.get("query_count"))
            current["query_count"] += query_count
            current["top5_count"] += _int(row.get("top5_count"))
            current["mention_count"] += round(_percent(row.get("model_mention_rate")) * query_count / 100)

    metrics = []
    for brand, values in grouped.items():
        query_count = int(values["query_count"])
        top5_count = int(values["top5_count"])
        mention_count = int(values["mention_count"])
        top5_share = (top5_count / query_count * 100) if query_count else 0.0
        mention_rate = (mention_count / query_count * 100) if query_count else 0.0
        metrics.append(
            BrandMetric(
                brand=brand,
                top5_share=round(top5_share, 2),
                model_mention_rate=round(mention_rate, 2),
                query_count=query_count,
                top5_count=top5_count,
            )
        )
    return sorted(metrics, key=lambda metric: (-metric.top5_share, -metric.model_mention_rate, metric.brand.lower()))


def _model_breakdowns(report_dir: Path) -> list[ModelBreakdown]:
    path = report_dir / "dimension_breakdown.csv"
    if not path.exists():
        return []
    items: list[ModelBreakdown] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("dimension") or "") != "model":
                continue
            items.append(
                ModelBreakdown(
                    model=str(row.get("value") or ""),
                    query_count=_int(row.get("query_count")),
                    target_top5_share=_percent(row.get("target_top5_share")),
                    leading_winner=str(row.get("leading_winner") or ""),
                    winner_count=_int(row.get("winner_count")),
                )
            )
    return items


def summarize_latest_report(project_root: Path | str = Path("."), target_brand: str = "AlphaXXXX") -> LatestReportSummary:
    root = Path(project_root)
    report_dir = _latest_merged_dir(root)
    if report_dir is None:
        return LatestReportSummary(None, 0, 0, None, None, None, [], [], [])

    return summarize_report_dir(report_dir, target_brand=target_brand)


def summarize_report_dir(report_dir: Path | str, target_brand: str = "AlphaXXXX") -> LatestReportSummary:
    report_dir = Path(report_dir)
    query_count, answer_count = _read_manifest_counts(report_dir)
    brands = _brand_metrics(report_dir)
    target = next((brand for brand in brands if brand.brand.lower() == target_brand.lower()), None)
    target_rank = None
    if target:
        for index, brand in enumerate(brands, start=1):
            if brand.brand.lower() == target_brand.lower():
                target_rank = index
                break
    brands_above = [brand for brand in brands if target and brand.top5_share > target.top5_share]

    return LatestReportSummary(
        report_dir=report_dir,
        query_count=query_count,
        answer_count=answer_count,
        target_top5_share=target.top5_share if target else None,
        target_model_mention_rate=target.model_mention_rate if target else None,
        target_rank_by_top5=target_rank,
        brands_above_target=brands_above,
        top_brands=brands[:5],
        model_breakdowns=_model_breakdowns(report_dir),
    )
