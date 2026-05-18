from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import read_jsonl


def load_vector_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    from FlagEmbedding import BGEM3FlagModel
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    return BGEM3FlagModel, QdrantClient, Distance, PointStruct, VectorParams


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def build_vector_index(
    input_path: Path,
    collection: str,
    qdrant_path: Path,
    embedding_model: str,
    status_output: Path,
    batch_size: int = 32,
    strict: bool = False,
    dependency_loader: Callable[[], tuple[Any, Any, Any, Any, Any]] = load_vector_dependencies,
) -> dict[str, Any]:
    try:
        BGEM3FlagModel, QdrantClient, Distance, PointStruct, VectorParams = dependency_loader()
    except ImportError as exc:
        status = {
            "status": "skipped",
            "reason": "missing_dependency",
            "error_message": str(exc),
            "input": str(input_path),
            "collection": collection,
            "qdrant_path": str(qdrant_path),
            "embedding_model": embedding_model,
        }
        write_status(status_output, status)
        if strict:
            raise SystemExit(1) from exc
        return status

    chunks = read_jsonl(input_path)
    model = BGEM3FlagModel(embedding_model, use_fp16=True)
    effective_batch_size = max(1, batch_size)
    first_batch = chunks[:effective_batch_size]
    first_batch_embeddings = model.encode([chunk["text"] for chunk in first_batch])["dense_vecs"] if first_batch else []
    vector_size = len(first_batch_embeddings[0]) if len(first_batch_embeddings) else 1024

    client = QdrantClient(path=str(qdrant_path))
    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    point_id = 1
    total_points = 0
    for batch_start in range(0, len(chunks), effective_batch_size):
        batch = chunks[batch_start : batch_start + effective_batch_size]
        if batch_start == 0:
            embeddings = first_batch_embeddings
        else:
            embeddings = model.encode([chunk["text"] for chunk in batch])["dense_vecs"]

        points = []
        for chunk, vector in zip(batch, embeddings):
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector.tolist() if hasattr(vector, "tolist") else vector,
                    payload={
                        key: chunk.get(key)
                        for key in (
                            "chunk_id",
                            "document_id",
                            "url",
                            "brand",
                            "title",
                            "source_type",
                            "page_type",
                            "heading",
                            "token_count",
                        )
                    }
                    | {"text": chunk.get("text", "")},
                )
            )
            point_id += 1
        if points:
            client.upsert(collection_name=collection, points=points)
            total_points += len(points)
    status = {
        "status": "indexed",
        "reason": None,
        "input": str(input_path),
        "collection": collection,
        "qdrant_path": str(qdrant_path),
        "embedding_model": embedding_model,
        "batch_size": effective_batch_size,
        "chunk_count": total_points,
    }
    write_status(status_output, status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Qdrant vector index.")
    parser.add_argument("--input", default="data/processed/chunks.jsonl")
    parser.add_argument("--collection", default="geo_chunks")
    parser.add_argument("--qdrant-path", default="vector_db/qdrant")
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--status-output", default="data/processed/vector_index_status.json")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    status = build_vector_index(
        input_path=Path(args.input),
        collection=args.collection,
        qdrant_path=Path(args.qdrant_path),
        embedding_model=args.embedding_model,
        status_output=Path(args.status_output),
        batch_size=args.batch_size,
        strict=args.strict,
    )
    if status["status"] == "indexed":
        print(f"Indexed {status['chunk_count']} chunks into Qdrant collection {args.collection}")
    else:
        print(f"Skipped vector index: {status['reason']} ({status['error_message']})")


if __name__ == "__main__":
    main()
