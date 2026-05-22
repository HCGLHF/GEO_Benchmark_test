import csv
from pathlib import Path

import pytest

from scripts.compare_llms_ab_reports import compare_runs, render_markdown


def write_brand_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "provider",
        "model",
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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_compare_runs_calculates_target_lift(tmp_path: Path):
    with_dir = tmp_path / "with"
    without_dir = tmp_path / "without"
    base = {
        "provider": "openrouter",
        "model": "model-a",
        "brand": "AlphaXXXX",
        "is_target": "True",
        "top1_count": "0",
        "top10_count": "0",
        "top10_slot_count": "0",
        "top5_query_share": "",
        "top10_query_share": "",
        "best_rank": "1",
        "average_best_rank": "1.00",
        "model_mention_rate": "",
        "unique_url_count": "1",
        "top_urls_json": '["https://alphaxxxx.com/llms.txt"]',
    }
    write_brand_rows(with_dir / "brand_performance_by_model.csv", [base | {"query_count": "100", "top5_count": "20", "model_mention_count": "15"}])
    write_brand_rows(without_dir / "brand_performance_by_model.csv", [base | {"query_count": "100", "top5_count": "8", "model_mention_count": "5", "top_urls_json": '["https://alphaxxxx.com/geo-pricing"]'}])

    result = compare_runs(with_dir, without_dir, target_brand="AlphaXXXX")

    assert result["with_llms"]["top5_share"] == 0.20
    assert result["without_llms"]["top5_share"] == 0.08
    assert result["delta"]["top5_share"] == pytest.approx(0.12)
    assert result["delta"]["model_mention_rate"] == pytest.approx(0.10)
    markdown = render_markdown(result)
    assert "llms.txt Lift Report" in markdown
    assert "12.0 pp" in markdown
