from __future__ import annotations

from collections.abc import Iterable
from typing import Any


MOJIBAKE_MARKERS = (
    "�",
    "æ¶",
    "æµ",
    "éˆ",
    "é¦",
    "ç’",
    "î…",
    "î„",
    "î†",
    "î",
)


def _duplicates(rows: Iterable[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_seen: set[str] = set()
    for row in rows:
        value = str(row.get(key, "") or "")
        if not value:
            continue
        if value in seen and value not in duplicate_seen:
            duplicates.append(value)
            duplicate_seen.add(value)
        seen.add(value)
    return duplicates


def _missing_fields(
    rows: Iterable[dict[str, Any]],
    *,
    id_field: str,
    required_fields: list[str],
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for row in rows:
        fields = sorted(
            field for field in required_fields if not str(row.get(field, "") or "").strip()
        )
        if fields:
            missing.append({id_field: str(row.get(id_field, "") or ""), "fields": fields})
    return missing


def _has_mojibake(value: Any) -> bool:
    text = str(value or "")
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def _mojibake_rows(
    rows: Iterable[dict[str, Any]],
    *,
    record_type: str,
    id_field: str,
    fields: list[str],
) -> list[dict[str, str]]:
    flagged: list[dict[str, str]] = []
    for row in rows:
        for field in fields:
            if _has_mojibake(row.get(field)):
                flagged.append(
                    {
                        "record_type": record_type,
                        "id": str(row.get(id_field, "") or ""),
                        "field": field,
                    }
                )
                break
    return flagged


def audit_corpus(
    inventory: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    document_ids = {str(row.get("document_id", "") or "") for row in documents}
    orphan_chunk_ids = [
        str(row.get("chunk_id", "") or "")
        for row in chunks
        if str(row.get("document_id", "") or "") not in document_ids
    ]
    report: dict[str, Any] = {
        "counts": {
            "inventory_rows": len(inventory),
            "documents": len(documents),
            "chunks": len(chunks),
        },
        "duplicate_inventory_urls": _duplicates(inventory, "url"),
        "duplicate_document_ids": _duplicates(documents, "document_id"),
        "duplicate_chunk_ids": _duplicates(chunks, "chunk_id"),
        "orphan_chunk_ids": orphan_chunk_ids,
        "missing_document_fields": _missing_fields(
            documents,
            id_field="document_id",
            required_fields=["document_id", "url", "brand", "content"],
        ),
        "missing_chunk_fields": _missing_fields(
            chunks,
            id_field="chunk_id",
            required_fields=["chunk_id", "document_id", "url", "brand", "text"],
        ),
        "mojibake_rows": [
            *_mojibake_rows(
                documents,
                record_type="document",
                id_field="document_id",
                fields=["title", "description", "content"],
            ),
            *_mojibake_rows(
                chunks,
                record_type="chunk",
                id_field="chunk_id",
                fields=["heading", "text"],
            ),
        ],
    }
    blocking_issue_count = sum(
        len(report[key])
        for key in (
            "duplicate_inventory_urls",
            "duplicate_document_ids",
            "duplicate_chunk_ids",
            "orphan_chunk_ids",
            "missing_document_fields",
            "missing_chunk_fields",
            "mojibake_rows",
        )
    )
    report["blocking_issue_count"] = blocking_issue_count
    report["is_import_safe"] = blocking_issue_count == 0
    return report
