import csv

from scripts.generate_report import load_csv


def test_load_csv_allows_large_result_fields(tmp_path):
    path = tmp_path / "results.csv"
    large_field = "x" * 200_000
    path.write_text(f"query_id,matched_urls_json\nq1,{large_field}\n", encoding="utf-8")
    original_limit = csv.field_size_limit()
    csv.field_size_limit(1024)
    try:
        rows = load_csv(path)
    finally:
        csv.field_size_limit(original_limit)

    assert rows[0]["matched_urls_json"] == large_field
