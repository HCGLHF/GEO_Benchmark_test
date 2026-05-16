from pathlib import Path

from scripts._common import write_jsonl
from scripts.chunk_documents import chunk_documents, split_text, token_count


def test_english_chunks_stay_within_expected_size_when_possible():
    paragraphs = ["word " * 120 for _ in range(5)]
    chunks = split_text("\n\n".join(paragraphs))

    assert len(chunks) >= 2
    assert all(token_count(chunk) <= 500 for chunk in chunks)


def test_long_single_line_english_text_is_split_within_expected_size():
    chunks = split_text(" ".join(f"word{i}" for i in range(1400)))

    assert len(chunks) >= 3
    assert all(token_count(chunk) <= 500 for chunk in chunks)


def test_chinese_chunks_stay_within_expected_size_when_possible():
    paragraphs = ["内容" * 180 for _ in range(4)]
    chunks = split_text("\n".join(paragraphs))

    assert len(chunks) >= 2
    assert all(token_count(chunk) <= 800 for chunk in chunks)


def test_long_single_line_chinese_text_is_split_within_expected_size():
    chunks = split_text("内容" * 1000)

    assert len(chunks) >= 2
    assert all(token_count(chunk) <= 800 for chunk in chunks)


def test_faq_pair_stays_together():
    chunks = split_text("What is this product?\nIt helps teams test GEO visibility.\nOther note.")

    assert "What is this product?\nIt helps teams test GEO visibility." in chunks[0]


def test_chunk_records_include_required_metadata(tmp_path: Path):
    documents_path = tmp_path / "documents.jsonl"
    write_jsonl(
        documents_path,
        [
            {
                "document_id": "doc_1",
                "url": "https://example.com/product",
                "site": "example.com",
                "brand": "Own",
                "title": "Product",
                "description": None,
                "content": "This product helps teams test GEO visibility. " * 30,
                "source_type": "official_site",
                "page_type": "product_page",
                "collected_at": "2026-05-15T00:00:00Z",
                "content_hash": "abc",
            }
        ],
    )

    chunks = chunk_documents(documents_path)

    assert chunks
    chunk = chunks[0]
    assert chunk.chunk_id.startswith("chunk_")
    assert chunk.document_id == "doc_1"
    assert chunk.url == "https://example.com/product"
    assert chunk.brand == "Own"
    assert chunk.title == "Product"
    assert chunk.text
    assert chunk.source_type == "official_site"
    assert chunk.page_type == "product_page"
    assert chunk.token_count > 0
