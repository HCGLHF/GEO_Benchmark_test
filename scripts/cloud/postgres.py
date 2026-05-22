from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _connect(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary] to import the corpus into PostgreSQL.") from exc
    return psycopg.connect(database_url)


def execute_schema(database_url: str, schema_path: Path) -> None:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_path.read_text(encoding="utf-8"))
        connection.commit()


def fetch_corpus_counts(database_url: str, corpus_version: str) -> dict[str, int]:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT inventory_count, document_count, chunk_count
                FROM corpus_versions
                WHERE corpus_version = %s
                """,
                (corpus_version,),
            )
            version_row = cursor.fetchone()
            if version_row is None:
                raise ValueError(f"Corpus version not found: {corpus_version}")
            cursor.execute(
                "SELECT count(*) FROM url_inventory WHERE corpus_version = %s",
                (corpus_version,),
            )
            inventory_rows = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM documents WHERE corpus_version = %s",
                (corpus_version,),
            )
            documents = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM chunks WHERE corpus_version = %s",
                (corpus_version,),
            )
            chunks = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM artifact_objects WHERE corpus_version = %s",
                (corpus_version,),
            )
            artifacts = cursor.fetchone()[0]
    return {
        "corpus_inventory_count": version_row[0],
        "corpus_document_count": version_row[1],
        "corpus_chunk_count": version_row[2],
        "inventory_rows": inventory_rows,
        "documents": documents,
        "chunks": chunks,
        "artifacts": artifacts,
    }


def fetch_artifact_rows(database_url: str, corpus_version: str) -> list[dict[str, Any]]:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_type, bucket, object_key, sha256, size_bytes, source_path, created_at
                FROM artifact_objects
                WHERE corpus_version = %s
                ORDER BY artifact_type, object_key
                """,
                (corpus_version,),
            )
            rows = cursor.fetchall()
    return [
        {
            "artifact_type": row[0],
            "bucket": row[1],
            "object_key": row[2],
            "sha256": row[3],
            "size_bytes": row[4],
            "source_path": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def _execute_many(cursor: Any, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    cursor.executemany(sql, list(rows))


def _artifact_rows(artifacts: Iterable[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            artifact.get("corpus_version"),
            artifact.get("artifact_type"),
            artifact.get("bucket"),
            artifact.get("object_key"),
            artifact.get("sha256"),
            artifact.get("size_bytes"),
            artifact.get("source_path"),
            artifact.get("created_at"),
        )
        for artifact in artifacts
    ]


ARTIFACT_OBJECTS_UPSERT_SQL = """
INSERT INTO artifact_objects (
  corpus_version, artifact_type, bucket, object_key,
  sha256, size_bytes, source_path, created_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (corpus_version, artifact_type, object_key) DO UPDATE SET
  bucket = EXCLUDED.bucket,
  sha256 = EXCLUDED.sha256,
  size_bytes = EXCLUDED.size_bytes,
  source_path = EXCLUDED.source_path,
  created_at = EXCLUDED.created_at
"""


def register_artifact_objects(database_url: str, artifacts: list[dict[str, Any]]) -> None:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            _execute_many(cursor, ARTIFACT_OBJECTS_UPSERT_SQL, _artifact_rows(artifacts))
        connection.commit()


def upsert_core_corpus(
    *,
    database_url: str,
    corpus_version: str,
    inventory: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> None:
    with _connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO corpus_versions (
                  corpus_version, inventory_count, document_count, chunk_count
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (corpus_version) DO UPDATE SET
                  inventory_count = EXCLUDED.inventory_count,
                  document_count = EXCLUDED.document_count,
                  chunk_count = EXCLUDED.chunk_count
                """,
                (corpus_version, len(inventory), len(documents), len(chunks)),
            )
            _execute_many(
                cursor,
                """
                INSERT INTO url_inventory (
                  corpus_version, url, brand, source_type, source_group,
                  seed_url, discovery_method, depth, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::integer, %s)
                ON CONFLICT (corpus_version, url) DO UPDATE SET
                  brand = EXCLUDED.brand,
                  source_type = EXCLUDED.source_type,
                  source_group = EXCLUDED.source_group,
                  seed_url = EXCLUDED.seed_url,
                  discovery_method = EXCLUDED.discovery_method,
                  depth = EXCLUDED.depth,
                  status = EXCLUDED.status
                """,
                (
                    (
                        corpus_version,
                        row.get("url"),
                        row.get("brand"),
                        row.get("source_type"),
                        row.get("source_group"),
                        row.get("seed_url"),
                        row.get("discovery_method"),
                        row.get("depth", ""),
                        row.get("status"),
                    )
                    for row in inventory
                ),
            )
            _execute_many(
                cursor,
                """
                INSERT INTO documents (
                  corpus_version, document_id, url, site, brand, title,
                  description, content, source_type, page_type, collected_at, content_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (corpus_version, document_id) DO UPDATE SET
                  url = EXCLUDED.url,
                  site = EXCLUDED.site,
                  brand = EXCLUDED.brand,
                  title = EXCLUDED.title,
                  description = EXCLUDED.description,
                  content = EXCLUDED.content,
                  source_type = EXCLUDED.source_type,
                  page_type = EXCLUDED.page_type,
                  collected_at = EXCLUDED.collected_at,
                  content_hash = EXCLUDED.content_hash
                """,
                (
                    (
                        corpus_version,
                        row.get("document_id"),
                        row.get("url"),
                        row.get("site"),
                        row.get("brand"),
                        row.get("title"),
                        row.get("description"),
                        row.get("content"),
                        row.get("source_type"),
                        row.get("page_type"),
                        row.get("collected_at"),
                        row.get("content_hash"),
                    )
                    for row in documents
                ),
            )
            _execute_many(
                cursor,
                """
                INSERT INTO chunks (
                  corpus_version, chunk_id, document_id, url, brand, title,
                  heading, text, source_type, page_type, token_count, content_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (corpus_version, chunk_id) DO UPDATE SET
                  document_id = EXCLUDED.document_id,
                  url = EXCLUDED.url,
                  brand = EXCLUDED.brand,
                  title = EXCLUDED.title,
                  heading = EXCLUDED.heading,
                  text = EXCLUDED.text,
                  source_type = EXCLUDED.source_type,
                  page_type = EXCLUDED.page_type,
                  token_count = EXCLUDED.token_count,
                  content_hash = EXCLUDED.content_hash
                """,
                (
                    (
                        corpus_version,
                        row.get("chunk_id"),
                        row.get("document_id"),
                        row.get("url"),
                        row.get("brand"),
                        row.get("title"),
                        row.get("heading"),
                        row.get("text"),
                        row.get("source_type"),
                        row.get("page_type"),
                        row.get("token_count"),
                        row.get("content_hash"),
                    )
                    for row in chunks
                ),
            )
            _execute_many(cursor, ARTIFACT_OBJECTS_UPSERT_SQL, _artifact_rows(artifacts))
        connection.commit()
