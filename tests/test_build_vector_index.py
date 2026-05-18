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


def test_vector_index_batches_embeddings_and_upserts(tmp_path: Path):
    chunks_path = tmp_path / "chunks.jsonl"
    status_path = tmp_path / "vector_index_status.json"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": f"c{index}",
                "document_id": f"d{index}",
                "url": f"https://example.com/{index}",
                "brand": "Example",
                "title": "Example",
                "heading": None,
                "text": f"Chunk {index}",
                "source_type": "competitor_site",
                "page_type": "unknown",
                "token_count": 2,
                "content_hash": "abc",
            }
            for index in range(5)
        ],
    )

    encode_batch_sizes = []
    upsert_batch_sizes = []

    class FakeModel:
        def __init__(self, embedding_model: str, use_fp16: bool = True) -> None:
            self.embedding_model = embedding_model

        def encode(self, texts):
            encode_batch_sizes.append(len(texts))

            class FakeVector(list):
                def tolist(self):
                    return list(self)

            return {"dense_vecs": [FakeVector([float(len(text)), 1.0]) for text in texts]}

    class FakeDistance:
        COSINE = "cosine"

    class FakeVectorParams:
        def __init__(self, size: int, distance: str) -> None:
            self.size = size
            self.distance = distance

    class FakePointStruct:
        def __init__(self, id: int, vector, payload) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def recreate_collection(self, collection_name: str, vectors_config) -> None:
            assert collection_name == "geo_chunks"
            assert vectors_config.size == 2

        def upsert(self, collection_name: str, points) -> None:
            upsert_batch_sizes.append(len(points))

    status = build_vector_index(
        input_path=chunks_path,
        collection="geo_chunks",
        qdrant_path=tmp_path / "qdrant",
        embedding_model="fake-model",
        status_output=status_path,
        batch_size=2,
        dependency_loader=lambda: (FakeModel, FakeClient, FakeDistance, FakePointStruct, FakeVectorParams),
    )

    assert encode_batch_sizes == [2, 2, 1]
    assert upsert_batch_sizes == [2, 2, 1]
    assert status["status"] == "indexed"
    assert status["chunk_count"] == 5
    assert status["batch_size"] == 2
