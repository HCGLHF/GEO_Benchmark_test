from pathlib import Path

from scripts.ui_app.corpus_summary import summarize_local_corpus


def test_summarize_local_corpus_counts_companies_urls_docs_and_chunks(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)

    (raw_dir / "url_inventory.csv").write_text(
        "url,brand\n"
        "https://a.example/,Alpha\n"
        "https://b.example/,Beta\n"
        "https://a.example/pricing,Alpha\n",
        encoding="utf-8",
    )
    (processed_dir / "documents.jsonl").write_text(
        '{"document_id":"doc-a","url":"https://a.example/","brand":"Alpha"}\n'
        '{"document_id":"doc-b","url":"https://b.example/","brand":"Beta"}\n',
        encoding="utf-8",
    )
    (processed_dir / "chunks.jsonl").write_text(
        '{"chunk_id":"chunk-a","document_id":"doc-a","brand":"Alpha"}\n'
        '{"chunk_id":"chunk-b","document_id":"doc-b","brand":"Beta"}\n'
        '{"chunk_id":"chunk-c","document_id":"doc-b","brand":"Beta"}\n',
        encoding="utf-8",
    )

    summary = summarize_local_corpus(tmp_path)

    assert summary.company_count == 2
    assert summary.url_count == 3
    assert summary.document_count == 2
    assert summary.chunk_count == 3
    assert summary.inventory_path == raw_dir / "url_inventory.csv"


def test_summarize_local_corpus_uses_documents_when_inventory_is_missing(tmp_path: Path) -> None:
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "documents.jsonl").write_text(
        '{"document_id":"doc-a","url":"https://a.example/","brand":"Alpha"}\n'
        '{"document_id":"doc-b","url":"https://b.example/","brand":"Beta"}\n',
        encoding="utf-8",
    )

    summary = summarize_local_corpus(tmp_path)

    assert summary.company_count == 2
    assert summary.url_count == 2
    assert summary.document_count == 2
