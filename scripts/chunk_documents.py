from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import ChunkRecord, content_hash, read_jsonl, stable_id, write_jsonl


CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CHINESE_SENTENCE_RE = re.compile(r"(?<=[。！？!?])")


def contains_chinese(text: str) -> bool:
    return bool(CHINESE_RE.search(text))


def token_count(text: str) -> int:
    if contains_chinese(text):
        return len(CHINESE_RE.findall(text))
    return len(text.split())


def merge_faq_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index].strip()
        if current.endswith(("?", "？")) and index + 1 < len(lines):
            merged.append(current + "\n" + lines[index + 1].strip())
            index += 2
        else:
            if current:
                merged.append(current)
            index += 1
    return merged


def pack_units(units: list[str], max_size: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        if not unit.strip():
            continue
        candidate = "\n\n".join(current + [unit])
        if current and token_count(candidate) > max_size:
            chunks.append("\n\n".join(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def split_long_unit(unit: str, max_size: int) -> list[str]:
    unit = unit.strip()
    if token_count(unit) <= max_size:
        return [unit] if unit else []

    if contains_chinese(unit):
        sentences = [part.strip() for part in CHINESE_SENTENCE_RE.split(unit) if part.strip()]
        if len(sentences) > 1:
            split_sentences: list[str] = []
            for sentence in sentences:
                split_sentences.extend(split_long_unit(sentence, max_size))
            return pack_units(split_sentences, max_size)
        return [unit[index : index + max_size] for index in range(0, len(unit), max_size)]

    sentences = [part.strip() for part in ENGLISH_SENTENCE_RE.split(unit) if part.strip()]
    if len(sentences) > 1:
        split_sentences = []
        for sentence in sentences:
            split_sentences.extend(split_long_unit(sentence, max_size))
        return pack_units(split_sentences, max_size)

    words = unit.split()
    return [" ".join(words[index : index + max_size]) for index in range(0, len(words), max_size)]


def split_text(text: str) -> list[str]:
    units = merge_faq_lines([line for line in text.splitlines() if line.strip()])
    if not units:
        units = [text]

    max_size = 800 if contains_chinese(text) else 500
    min_size = 300 if contains_chinese(text) else 200
    expanded_units: list[str] = []
    for unit in units:
        expanded_units.extend(split_long_unit(unit, max_size))

    chunks: list[str] = []
    current: list[str] = []

    for unit in expanded_units:
        candidate = "\n\n".join(current + [unit])
        if current and token_count(candidate) > max_size:
            chunks.append("\n\n".join(current))
            current = [unit]
        else:
            current.append(unit)

    if current:
        tail = "\n\n".join(current)
        merged_tail = chunks[-1] + "\n\n" + tail if chunks else tail
        if chunks and token_count(tail) < min_size and token_count(merged_tail) <= max_size:
            chunks[-1] = merged_tail
        else:
            chunks.append(tail)

    return [chunk for chunk in chunks if chunk.strip()]


def chunk_documents(documents_path: Path) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for doc in read_jsonl(documents_path):
        for index, text in enumerate(split_text(doc["content"]), start=1):
            chunk_id = stable_id("chunk", f"{doc['document_id']}:{index}:{text}")
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=doc["document_id"],
                    url=doc["url"],
                    brand=doc.get("brand", ""),
                    title=doc.get("title", ""),
                    heading=None,
                    text=text,
                    source_type=doc.get("source_type", ""),
                    page_type=doc.get("page_type", "unknown"),
                    token_count=token_count(text),
                    content_hash=content_hash(text),
                )
            )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk cleaned documents for retrieval.")
    parser.add_argument("--input", default="data/processed/documents.jsonl")
    parser.add_argument("--output", default="data/processed/chunks.jsonl")
    args = parser.parse_args()

    chunks = chunk_documents(Path(args.input))
    write_jsonl(Path(args.output), chunks)
    print(f"Wrote {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
