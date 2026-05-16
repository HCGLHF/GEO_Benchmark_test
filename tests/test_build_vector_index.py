from pathlib import Path

from scripts.build_vector_index import build_vector_index
from scripts._common import write_jsonl


def test_vector_index_skips_missing_dependencies_when_not_strict(tmp_path: Path):
    chunks_path = tmp_path / "chunks.jsonl"
    status_path = tmp_path / "vector_index_status.json"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "url": "https://example.com",
                "brand": "Own",
                "title": "Example",
                "heading": None,
                "text": "Useful GEO benchmark content.",
                "source_type": "official_site",
                "page_type": "home",
                "token_count": 4,
                "content_hash": "abc",
            }
        ],
    )

    status = build_vector_index(
        input_path=chunks_path,
        collection="geo_chunks",
        qdrant_path=tmp_path / "qdrant",
        embedding_model="BAAI/bge-m3",
        status_output=status_path,
        strict=False,
        dependency_loader=lambda: (_ for _ in ()).throw(ImportError("No module named 'FlagEmbedding'")),
    )

    assert status["status"] == "skipped"
    assert status["reason"] == "missing_dependency"
    assert status_path.exists()


def test_vector_index_raises_missing_dependencies_when_strict(tmp_path: Path):
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(chunks_path, [])

    try:
        build_vector_index(
            input_path=chunks_path,
            collection="geo_chunks",
            qdrant_path=tmp_path / "qdrant",
            embedding_model="BAAI/bge-m3",
            status_output=tmp_path / "status.json",
            strict=True,
            dependency_loader=lambda: (_ for _ in ()).throw(ImportError("No module named 'FlagEmbedding'")),
        )
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("strict vector index should fail when dependencies are missing")
