import json
import pickle
from pathlib import Path

import yaml

from scripts.build_corpus_variant import build_without_llms_variant


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_build_without_llms_variant_filters_llms_and_writes_config(tmp_path: Path):
    processed = tmp_path / "processed"
    write_jsonl(
        processed / "documents.jsonl",
        [
            {"document_id": "d1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com/llms.txt"},
            {"document_id": "d2", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com/geo-pricing"},
            {"document_id": "d3", "brand": "HornTech", "url": "https://horntech.com.au"},
        ],
    )
    write_jsonl(
        processed / "chunks.jsonl",
        [
            {"chunk_id": "c1", "document_id": "d1", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com/llms.txt", "text": "llms router"},
            {"chunk_id": "c2", "document_id": "d2", "brand": "AlphaXXXX", "url": "https://alphaxxxx.com/geo-pricing", "text": "geo pricing australia"},
            {"chunk_id": "c3", "document_id": "d3", "brand": "HornTech", "url": "https://horntech.com.au", "text": "horntech"},
        ],
    )
    write_jsonl(
        processed / "page_signals.jsonl",
        [
            {"url": "https://alphaxxxx.com/llms.txt"},
            {"url": "https://alphaxxxx.com/geo-pricing"},
        ],
    )
    write_jsonl(
        processed / "evidence_cards.jsonl",
        [
            {"url": "https://alphaxxxx.com/llms.txt"},
            {"url": "https://alphaxxxx.com/geo-pricing"},
        ],
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "retrieval": {
                    "keyword_index": str(processed / "bm25_index.pkl"),
                    "evidence_cards": str(processed / "evidence_cards.jsonl"),
                    "page_signals": str(processed / "page_signals.jsonl"),
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = build_without_llms_variant(
        source_processed_dir=processed,
        output_dir=tmp_path / "variants" / "without_llms",
        base_config_path=config_path,
        output_config_path=tmp_path / "config.without_llms.yaml",
    )

    assert result["removed_documents"] == 1
    assert result["removed_chunks"] == 1
    docs = [json.loads(line) for line in Path(result["documents"]).read_text(encoding="utf-8").splitlines()]
    chunks = [json.loads(line) for line in Path(result["chunks"]).read_text(encoding="utf-8").splitlines()]
    assert [row["url"] for row in docs] == ["https://alphaxxxx.com/geo-pricing", "https://horntech.com.au"]
    assert [row["url"] for row in chunks] == ["https://alphaxxxx.com/geo-pricing", "https://horntech.com.au"]
    with Path(result["keyword_index"]).open("rb") as handle:
        artifact = pickle.load(handle)
    assert [row["chunk_id"] for row in artifact["chunks"]] == ["c2", "c3"]
    written_config = yaml.safe_load((tmp_path / "config.without_llms.yaml").read_text(encoding="utf-8"))
    assert written_config["retrieval"]["documents"] == result["documents"]
    assert written_config["retrieval"]["chunks"] == result["chunks"]
    assert written_config["retrieval"]["keyword_index"] == result["keyword_index"]
