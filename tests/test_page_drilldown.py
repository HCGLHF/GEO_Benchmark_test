from pathlib import Path

from scripts.page_drilldown import (
    PAGE_DRILLDOWN_FIELDS,
    build_owned_page_drilldown,
    load_owned_pages,
    render_owned_page_sections,
)


def test_build_owned_page_drilldown_counts_target_top5_pages_and_weak_pages() -> None:
    evidence = [
        {
            "query_id": "q001",
            "model": "openai/gpt-4.1-mini",
            "persona": "founder",
            "journey_stage": "problem_aware",
            "retrieved_chunks": [
                {"brand": "Competitor", "url": "https://competitor.example/a", "title": "Competitor"},
                {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/service", "title": "Service"},
                {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/blog/guide", "title": "Guide"},
                {"brand": "Competitor", "url": "https://competitor.example/b", "title": "Competitor"},
                {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/service", "title": "Service"},
            ],
        },
        {
            "query_id": "q002",
            "model": "google/gemini-2.5-flash",
            "persona": "founder",
            "journey_stage": "solution_aware",
            "retrieved_chunks": [
                {"brand": "Competitor", "url": "https://competitor.example/a", "title": "Competitor"},
                {"brand": "Competitor", "url": "https://competitor.example/b", "title": "Competitor"},
                {"brand": "Competitor", "url": "https://competitor.example/c", "title": "Competitor"},
                {"brand": "Competitor", "url": "https://competitor.example/d", "title": "Competitor"},
                {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/blog/guide", "title": "Guide"},
            ],
        },
    ]
    owned_pages = [
        {"url": "https://alphaxxxx.com/service", "title": "Service"},
        {"url": "https://alphaxxxx.com/blog/guide", "title": "Guide"},
        {"url": "https://alphaxxxx.com/blog/never-seen", "title": "Never Seen"},
    ]

    result = build_owned_page_drilldown("AlphaXXXX", evidence, owned_pages=owned_pages)

    assert result.top_pages[0]["url"] == "https://alphaxxxx.com/blog/guide"
    assert result.top_pages[0]["top5_query_count"] == 2
    assert result.top_pages[0]["best_rank"] == 3
    assert result.top_pages[0]["model_count"] == 2
    assert result.weak_pages[0]["url"] == "https://alphaxxxx.com/blog/never-seen"
    assert result.weak_pages[0]["top5_query_count"] == 0
    assert "No Top5 retrieval" in result.weak_pages[0]["optimization_hint"]


def test_load_owned_pages_reads_documents_jsonl(tmp_path: Path) -> None:
    documents = tmp_path / "documents.jsonl"
    documents.write_text(
        '{"url":"https://alphaxxxx.com/","brand":"AlphaXXXX","title":"Home","content":"long text"}\n'
        '{"url":"https://competitor.example/","brand":"Competitor","title":"Other"}\n',
        encoding="utf-8",
    )

    pages = load_owned_pages(documents, "AlphaXXXX")

    assert pages == [{"url": "https://alphaxxxx.com/", "title": "Home", "content_length": 9}]


def test_render_owned_page_sections_adds_markdown_tables() -> None:
    result = build_owned_page_drilldown(
        "AlphaXXXX",
        [
            {
                "query_id": "q001",
                "model": "openai/gpt-4.1-mini",
                "retrieved_chunks": [
                    {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/service", "title": "Service"}
                ],
            }
        ],
        owned_pages=[{"url": "https://alphaxxxx.com/service", "title": "Service"}],
    )

    markdown = render_owned_page_sections("AlphaXXXX", result)

    assert "## AlphaXXXX Top5 Retrieved Pages" in markdown
    assert "## AlphaXXXX Weak Pages To Optimize" in markdown
    assert "https://alphaxxxx.com/service" in markdown
    assert PAGE_DRILLDOWN_FIELDS[0] == "url"


def test_render_owned_page_sections_truncates_long_titles() -> None:
    long_title = "AlphaXXXX " * 80
    result = build_owned_page_drilldown(
        "AlphaXXXX",
        [
            {
                "query_id": "q001",
                "model": "openai/gpt-4.1-mini",
                "retrieved_chunks": [
                    {"brand": "AlphaXXXX", "url": "https://alphaxxxx.com/llms.txt", "title": long_title}
                ],
            }
        ],
    )

    markdown = render_owned_page_sections("AlphaXXXX", result)

    assert long_title not in markdown
    assert "AlphaXXXX AlphaXXXX" in markdown
    assert "..." in markdown
