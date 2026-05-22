import csv
import json
from pathlib import Path

from scripts.cloud.import_corpus import build_import_plan
from scripts.cloud.s3_artifacts import artifact_key, build_artifact_record


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_artifact_key_uses_type_version_and_filename():
    assert (
        artifact_key(
            "geo-agency",
            "processed",
            "2026-05-22-initial",
            Path("data/processed/documents.jsonl"),
        )
        == "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl"
    )


def test_build_artifact_record_hashes_local_file(tmp_path: Path):
    path = tmp_path / "documents.jsonl"
    path.write_text('{"document_id":"doc_1"}\n', encoding="utf-8")

    record = build_artifact_record(
        industry_id="geo-agency",
        artifact_type="processed_documents",
        corpus_version="2026-05-22-initial",
        path=path,
        prefix="processed",
    )

    assert record["industry_id"] == "geo-agency"
    assert record["artifact_type"] == "processed_documents"
    assert record["corpus_version"] == "2026-05-22-initial"
    assert record["object_key"] == "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl"
    assert record["size_bytes"] == path.stat().st_size
    assert len(record["sha256"]) == 64


def test_build_import_plan_reads_core_files_and_artifacts(tmp_path: Path):
    inventory_path = tmp_path / "data" / "raw" / "url_inventory.csv"
    documents_path = tmp_path / "data" / "processed" / "documents.jsonl"
    chunks_path = tmp_path / "data" / "processed" / "chunks.jsonl"
    write_csv(
        inventory_path,
        [
            {
                "url": "https://alpha.example/",
                "brand": "AlphaXXXX",
                "source_type": "official_site",
            }
        ],
    )
    write_jsonl(
        documents_path,
        [
            {
                "document_id": "doc_1",
                "url": "https://alpha.example/",
                "brand": "AlphaXXXX",
                "content": "Clean GEO content.",
            }
        ],
    )
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "url": "https://alpha.example/",
                "brand": "AlphaXXXX",
                "text": "A good chunk.",
            }
        ],
    )

    plan = build_import_plan(
        industry_id="geo-agency",
        corpus_version="2026-05-22-initial",
        inventory_path=inventory_path,
        documents_path=documents_path,
        chunks_path=chunks_path,
    )

    assert plan["industry_id"] == "geo-agency"
    assert plan["quality_report"]["is_import_safe"] is True
    assert plan["row_counts"] == {
        "inventory_rows": 1,
        "documents": 1,
        "chunks": 1,
        "artifacts": 3,
    }
    assert [artifact["artifact_type"] for artifact in plan["artifacts"]] == [
        "url_inventory",
        "processed_documents",
        "processed_chunks",
    ]
