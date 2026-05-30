import json
from pathlib import Path

from scripts.cloud.download_processed_corpus import download_processed_corpus


class FakeS3Client:
    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_text(self.objects[key], encoding="utf-8")


def test_download_processed_corpus_downloads_core_artifacts_and_rebuilds_local_indexes(tmp_path: Path) -> None:
    documents = [
        {
            "document_id": "doc_alpha",
            "url": "https://alphaxxxx.com/",
            "site": "alphaxxxx.com",
            "brand": "AlphaXXXX",
            "title": "Alpha",
            "content": "GEO visibility for SaaS brands.",
            "source_type": "owned_site",
            "page_type": "unknown",
            "collected_at": "2026-05-30T00:00:00Z",
            "content_hash": "hash",
        }
    ]
    chunks = [
        {
            "chunk_id": "chunk_alpha",
            "document_id": "doc_alpha",
            "url": "https://alphaxxxx.com/",
            "brand": "AlphaXXXX",
            "title": "Alpha",
            "heading": None,
            "text": "GEO visibility for SaaS brands.",
            "source_type": "owned_site",
            "page_type": "unknown",
            "token_count": 6,
            "content_hash": "hash",
        }
    ]
    rows = [
        {
            "artifact_type": "processed_documents",
            "bucket": "bucket",
            "object_key": "processed/documents.jsonl",
            "size_bytes": 1,
        },
        {
            "artifact_type": "processed_chunks",
            "bucket": "bucket",
            "object_key": "processed/chunks.jsonl",
            "size_bytes": 1,
        },
    ]

    result = download_processed_corpus(
        artifact_rows=rows,
        bucket="bucket",
        region="ap-northeast-1",
        processed_dir=tmp_path / "processed",
        s3_client=FakeS3Client(
            {
                "processed/documents.jsonl": "".join(json.dumps(row) + "\n" for row in documents),
                "processed/chunks.jsonl": "".join(json.dumps(row) + "\n" for row in chunks),
            }
        ),
    )

    assert result["documents"] == 1
    assert result["chunks"] == 1
    assert (tmp_path / "processed" / "documents.jsonl").exists()
    assert (tmp_path / "processed" / "chunks.jsonl").exists()
    assert (tmp_path / "processed" / "page_signals.jsonl").exists()
    assert (tmp_path / "processed" / "evidence_cards.jsonl").exists()
    assert (tmp_path / "processed" / "bm25_index.pkl").exists()
