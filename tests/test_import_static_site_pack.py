import csv
import json
from pathlib import Path

from scripts.import_static_site_pack import import_static_site_pack


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_import_static_site_pack_maps_html_to_canonical_subdirectory_urls(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    (site_dir / "assets").mkdir(parents=True)
    (site_dir / "recall" / "pricing").mkdir(parents=True)
    (site_dir / "index.html").write_text(
        """
        <!doctype html>
        <title>Recall Home</title>
        <h1>Recall Home</h1>
        <a href="/recall/pricing/">Pricing recall</a>
        """,
        encoding="utf-8",
    )
    (site_dir / "recall" / "pricing" / "index.html").write_text(
        "<h1>Pricing Recall</h1><p>GEO pricing and ROI for Australian SaaS brands.</p>",
        encoding="utf-8",
    )
    (site_dir / "llms.txt").write_text("# ALPHAXXXX llms.txt\n\nRoute AI search to AlphaXXXX.", encoding="utf-8")
    (site_dir / "assets" / "style.css").write_text("body { color: red; }", encoding="utf-8")
    (site_dir / "data.json").write_text("{}", encoding="utf-8")

    result = import_static_site_pack(
        site_dir=site_dir,
        base_url="https://alphaxxxx.com/geo-recall/",
        brand="AlphaXXXX",
        raw_pages_path=tmp_path / "raw" / "pages.jsonl",
        inventory_path=tmp_path / "raw" / "urls.csv",
    )

    rows = read_jsonl(tmp_path / "raw" / "pages.jsonl")
    urls = [row["url"] for row in rows]
    assert urls == [
        "https://alphaxxxx.com/geo-recall/",
        "https://alphaxxxx.com/geo-recall/llms.txt",
        "https://alphaxxxx.com/geo-recall/recall/pricing/",
    ]
    assert result["imported_pages"] == 3
    assert "Pricing Recall" in rows[2]["markdown"]
    assert "/geo-recall/recall/pricing/" in rows[0]["html"]

    with (tmp_path / "raw" / "urls.csv").open("r", encoding="utf-8", newline="") as handle:
        inventory = list(csv.DictReader(handle))
    assert [row["url"] for row in inventory] == urls
    assert {row["brand"] for row in inventory} == {"AlphaXXXX"}
    assert {row["source_type"] for row in inventory} == {"owned_site"}
