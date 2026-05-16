# GEO Resource Library

This project builds a private retrieval and generation benchmark for GEO optimization. It crawls owned, competitor, and industry pages, then evaluates whether owned content is retrieved, mentioned, cited, and recommended by LLM-style answer systems.

## MVP Pipeline

1. Configure sources and queries.
2. Crawl pages with tiered fetch methods.
3. Clean pages into documents.
4. Chunk documents.
5. Build vector and keyword indexes.
6. Run retrieval evaluation.
7. Run generation evaluation.
8. Generate a Markdown report.
