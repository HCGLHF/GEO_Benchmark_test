from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CorpusSummary:
    company_count: int
    url_count: int
    document_count: int
    chunk_count: int
    inventory_path: Path | None
    documents_path: Path | None
    chunks_path: Path | None
    alpha_document_count: int
    alpha_chunk_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("inventory_path", "documents_path", "chunks_path"):
            payload[key] = str(payload[key]) if payload[key] else None
        return payload


def _count_jsonl(path: Path) -> tuple[int, set[str], set[str]]:
    rows = 0
    brands: set[str] = set()
    urls: set[str] = set()
    if not path.exists():
        return rows, brands, urls
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            brand = str(record.get("brand") or "").strip()
            url = str(record.get("url") or "").strip()
            if brand:
                brands.add(brand)
            if url:
                urls.add(url)
    return rows, brands, urls


def _inventory_sets(path: Path) -> tuple[set[str], set[str]]:
    brands: set[str] = set()
    urls: set[str] = set()
    if not path.exists():
        return brands, urls
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            brand = str(row.get("brand") or "").strip()
            url = str(row.get("url") or "").strip()
            if brand:
                brands.add(brand)
            if url:
                urls.add(url)
    return brands, urls


def _count_alpha_rows(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"brand": "AlphaXXXX"' in line or '"brand":"AlphaXXXX"' in line:
                count += 1
    return count


def summarize_local_corpus(project_root: Path | str = Path(".")) -> CorpusSummary:
    root = Path(project_root)
    inventory_path = root / "data" / "raw" / "url_inventory.csv"
    documents_path = root / "data" / "processed" / "documents.jsonl"
    chunks_path = root / "data" / "processed" / "chunks.jsonl"

    inventory_brands, inventory_urls = _inventory_sets(inventory_path)
    document_count, document_brands, document_urls = _count_jsonl(documents_path)
    chunk_count, chunk_brands, _chunk_urls = _count_jsonl(chunks_path)

    brands = inventory_brands or document_brands or chunk_brands
    urls = inventory_urls or document_urls

    return CorpusSummary(
        company_count=len(brands),
        url_count=len(urls),
        document_count=document_count,
        chunk_count=chunk_count,
        inventory_path=inventory_path if inventory_path.exists() else None,
        documents_path=documents_path if documents_path.exists() else None,
        chunks_path=chunks_path if chunks_path.exists() else None,
        alpha_document_count=_count_alpha_rows(documents_path),
        alpha_chunk_count=_count_alpha_rows(chunks_path),
    )
