import json

from scripts.eval_retrieval import calculate_retrieval_metrics, compact_result_row, evidence_result_row


def test_owned_brand_rank_is_one_when_owned_content_first():
    result = calculate_retrieval_metrics(
        query_id="q1",
        query="best tools",
        target_brand="Own",
        top_k=10,
        results=[
            {"chunk_id": "c1", "brand": "Own", "source_type": "official_site", "url": "https://own.example"},
            {"chunk_id": "c2", "brand": "Competitor", "source_type": "competitor_site", "url": "https://comp.example"},
        ],
    )

    assert result.own_brand_rank == 1
    assert result.own_brand_in_top_3 is True


def test_owned_brand_in_top_five_at_rank_five():
    results = [
        {"chunk_id": f"c{i}", "brand": "Competitor", "source_type": "competitor_site", "url": f"https://c{i}.example"}
        for i in range(1, 5)
    ] + [
        {"chunk_id": "c5", "brand": "Own", "source_type": "official_site", "url": "https://own.example"}
    ]

    result = calculate_retrieval_metrics("q1", "query", "Own", results, 10)

    assert result.own_brand_rank == 5
    assert result.own_brand_in_top_5 is True
    assert result.own_brand_in_top_3 is False


def test_competitor_above_owned_when_competitor_appears_first():
    result = calculate_retrieval_metrics(
        "q1",
        "query",
        "Own",
        [
            {"chunk_id": "c1", "brand": "Competitor", "source_type": "competitor_site", "url": "https://comp.example"},
            {"chunk_id": "c2", "brand": "Own", "source_type": "official_site", "url": "https://own.example"},
        ],
        10,
    )

    assert result.competitor_above_owned is True


def test_winning_brand_is_rank_one_brand():
    result = calculate_retrieval_metrics(
        "q1",
        "query",
        "Own",
        [
            {"chunk_id": "c1", "brand": "Competitor", "source_type": "competitor_site", "url": "https://comp.example"},
            {"chunk_id": "c2", "brand": "Own", "source_type": "official_site", "url": "https://own.example"},
        ],
        10,
    )

    assert result.winning_brand == "Competitor"


def test_compact_result_row_keeps_metrics_without_full_chunks():
    result = calculate_retrieval_metrics(
        "q1",
        "query",
        "Own",
        [{"chunk_id": "c1", "brand": "Own", "source_type": "official_site", "url": "https://own.example", "text": "x" * 1000}],
        10,
    )

    row = compact_result_row(result)

    assert row["query_id"] == "q1"
    assert row["matched_urls_json"] == '["https://own.example"]'
    assert "retrieved_chunks_json" not in row


def test_evidence_result_row_preserves_retrieved_chunks_outside_csv():
    result = calculate_retrieval_metrics(
        "q1",
        "query",
        "Own",
        [{"chunk_id": "c1", "brand": "Own", "source_type": "official_site", "url": "https://own.example", "text": "x" * 1000}],
        10,
    )

    row = evidence_result_row(result)

    assert row["query_id"] == "q1"
    chunks = json.loads(row["retrieved_chunks_json"])
    assert chunks[0]["url"] == "https://own.example"
    assert len(chunks[0]["text"]) == 1000
