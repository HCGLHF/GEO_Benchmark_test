from scripts.cloud.corpus_quality import audit_corpus


def test_audit_corpus_flags_duplicates_orphans_missing_fields_and_mojibake():
    inventory = [
        {"url": "https://alpha.example/", "brand": "AlphaXXXX"},
        {"url": "https://alpha.example/", "brand": "AlphaXXXX"},
    ]
    documents = [
        {
            "document_id": "doc_1",
            "url": "https://alpha.example/",
            "brand": "AlphaXXXX",
            "content": "Clean GEO content.",
        },
        {
            "document_id": "doc_1",
            "url": "https://duplicate.example/",
            "brand": "Competitor",
            "content": "Duplicate document id.",
        },
        {
            "document_id": "doc_2",
            "url": "",
            "brand": "",
            "content": "Broken mojibake æ¶“ content.",
        },
    ]
    chunks = [
        {
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "url": "https://alpha.example/",
            "brand": "AlphaXXXX",
            "text": "A good chunk.",
        },
        {
            "chunk_id": "chunk_1",
            "document_id": "missing_doc",
            "url": "https://orphan.example/",
            "brand": "Competitor",
            "text": "This chunk has no document.",
        },
        {
            "chunk_id": "chunk_3",
            "document_id": "doc_2",
            "url": "https://mojibake.example/",
            "brand": "Competitor",
            "text": "More mojibake éˆ¥? text.",
        },
    ]

    report = audit_corpus(inventory, documents, chunks)

    assert report["counts"] == {
        "inventory_rows": 2,
        "documents": 3,
        "chunks": 3,
    }
    assert report["is_import_safe"] is False
    assert report["duplicate_inventory_urls"] == ["https://alpha.example/"]
    assert report["duplicate_document_ids"] == ["doc_1"]
    assert report["duplicate_chunk_ids"] == ["chunk_1"]
    assert report["orphan_chunk_ids"] == ["chunk_1"]
    assert report["missing_document_fields"] == [{"document_id": "doc_2", "fields": ["brand", "url"]}]
    assert report["mojibake_rows"] == [
        {"record_type": "document", "id": "doc_2", "field": "content"},
        {"record_type": "chunk", "id": "chunk_3", "field": "text"},
    ]


def test_audit_corpus_allows_clean_minimal_corpus():
    report = audit_corpus(
        inventory=[{"url": "https://alpha.example/", "brand": "AlphaXXXX"}],
        documents=[
            {
                "document_id": "doc_1",
                "url": "https://alpha.example/",
                "brand": "AlphaXXXX",
                "content": "Clean GEO content.",
            }
        ],
        chunks=[
            {
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "url": "https://alpha.example/",
                "brand": "AlphaXXXX",
                "text": "A good chunk.",
            }
        ],
    )

    assert report["is_import_safe"] is True
    assert report["blocking_issue_count"] == 0


def test_audit_corpus_does_not_flag_valid_french_accents():
    report = audit_corpus(
        inventory=[{"url": "https://example.fr/", "brand": "Example"}],
        documents=[
            {
                "document_id": "doc_fr",
                "url": "https://example.fr/",
                "brand": "Example",
                "content": "L'hébergement est fiable même avec des caractères accentués.",
            }
        ],
        chunks=[
            {
                "chunk_id": "chunk_fr",
                "document_id": "doc_fr",
                "url": "https://example.fr/",
                "brand": "Example",
                "text": "Le coût peut entraîner des décisions différentes.",
            }
        ],
    )

    assert report["mojibake_rows"] == []
    assert report["is_import_safe"] is True
