import json
from pathlib import Path

from scripts.refresh_owned_site_processed import refresh_owned_site_processed, target_domain_matches


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_target_domain_matches_www_and_bare_domain() -> None:
    assert target_domain_matches("https://alphaxxxx.com/blog/post", "alphaxxxx.com")
    assert target_domain_matches("https://www.alphaxxxx.com/blog/post", "alphaxxxx.com")
    assert not target_domain_matches("https://example.com/blog/post", "alphaxxxx.com")


def test_refresh_owned_site_processed_replaces_owned_docs_and_rebuilds_artifacts(tmp_path: Path) -> None:
    raw_pages = tmp_path / "raw" / "alpha_update_pages.jsonl"
    inventory = tmp_path / "raw" / "alpha_update_discovered_urls.csv"
    processed = tmp_path / "processed"
    write_jsonl(
        processed / "documents.jsonl",
        [
            {
                "document_id": "old-alpha",
                "url": "https://alphaxxxx.com/old",
                "site": "alphaxxxx.com",
                "brand": "AlphaXXXX",
                "title": "Old Alpha",
                "content": "old content",
                "source_type": "owned_site",
                "page_type": "unknown",
                "collected_at": "",
                "content_hash": "old",
            },
            {
                "document_id": "competitor",
                "url": "https://horntech.com.au/",
                "site": "horntech.com.au",
                "brand": "HornTech",
                "title": "HornTech",
                "content": "competitor content",
                "source_type": "competitor_site",
                "page_type": "unknown",
                "collected_at": "",
                "content_hash": "competitor",
            },
        ],
    )
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        "url,brand,source_type,source_group,seed_url,discovery_method,depth,status\n"
        "https://alphaxxxx.com/blog/new-post,AlphaXXXX,owned_site,own_site,https://alphaxxxx.com/,sitemap,0,discovered\n",
        encoding="utf-8",
    )
    write_jsonl(
        raw_pages,
        [
            {
                "url": "https://alphaxxxx.com/blog/new-post",
                "markdown": "# New Blog Post\n\nGenerative Engine Optimization for SaaS brands in Australia.",
                "collected_at": "2026-05-23T00:00:00Z",
            }
        ],
    )

    result = refresh_owned_site_processed(
        raw_pages_path=raw_pages,
        inventory_path=inventory,
        processed_dir=processed,
        target_domain="alphaxxxx.com",
    )

    documents = [json.loads(line) for line in (processed / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    urls = [row["url"] for row in documents]
    assert "https://alphaxxxx.com/old" not in urls
    assert "https://alphaxxxx.com/blog/new-post" in urls
    assert "https://horntech.com.au/" in urls
    assert result["replaced_owned_documents"] == 1
    assert result["incoming_owned_documents"] == 1
    assert (processed / "chunks.jsonl").exists()
    assert (processed / "page_signals.jsonl").exists()
    assert (processed / "evidence_cards.jsonl").exists()
    assert (processed / "bm25_index.pkl").exists()
    assert "https://alphaxxxx.com/blog/new-post" in (processed / "chunks.jsonl").read_text(encoding="utf-8")


def test_refresh_owned_site_processed_can_replace_only_url_prefix(tmp_path: Path) -> None:
    raw_pages = tmp_path / "raw" / "alpha_geo_recall_pages.jsonl"
    inventory = tmp_path / "raw" / "alpha_geo_recall_urls.csv"
    processed = tmp_path / "processed"
    write_jsonl(
        processed / "documents.jsonl",
        [
            {
                "document_id": "homepage",
                "url": "https://alphaxxxx.com/",
                "site": "alphaxxxx.com",
                "brand": "AlphaXXXX",
                "title": "Home",
                "content": "existing home content",
                "source_type": "owned_site",
                "page_type": "unknown",
                "collected_at": "",
                "content_hash": "home",
            },
            {
                "document_id": "old-recall",
                "url": "https://alphaxxxx.com/geo-recall/old",
                "site": "alphaxxxx.com",
                "brand": "AlphaXXXX",
                "title": "Old Recall",
                "content": "old recall content",
                "source_type": "owned_site",
                "page_type": "unknown",
                "collected_at": "",
                "content_hash": "old-recall",
            },
        ],
    )
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        "url,brand,source_type,source_group,seed_url,discovery_method,depth,status\n"
        "https://alphaxxxx.com/geo-recall/,AlphaXXXX,owned_site,own_site,https://alphaxxxx.com/geo-recall/,static_pack,0,discovered\n",
        encoding="utf-8",
    )
    write_jsonl(
        raw_pages,
        [
            {
                "url": "https://alphaxxxx.com/geo-recall/",
                "markdown": "# GEO Recall\n\nAI search recall pages for AlphaXXXX.",
                "collected_at": "2026-05-30T00:00:00Z",
            }
        ],
    )

    result = refresh_owned_site_processed(
        raw_pages_path=raw_pages,
        inventory_path=inventory,
        processed_dir=processed,
        target_domain="alphaxxxx.com",
        replace_url_prefix="https://alphaxxxx.com/geo-recall/",
    )

    documents = [json.loads(line) for line in (processed / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    urls = [row["url"] for row in documents]
    assert "https://alphaxxxx.com/" in urls
    assert "https://alphaxxxx.com/geo-recall/old" not in urls
    assert "https://alphaxxxx.com/geo-recall/" in urls
    assert result["replaced_owned_documents"] == 1
    assert result["incoming_owned_documents"] == 1
