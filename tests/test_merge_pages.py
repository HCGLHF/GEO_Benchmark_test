from scripts.merge_pages import merge_by_url


def test_merge_by_url_replaces_existing_with_newer_page():
    existing = [
        {"url": "https://example.com/", "markdown": "old"},
        {"url": "https://keep.example/", "markdown": "keep"},
    ]
    incoming = [
        {"url": "https://example.com/", "markdown": "new"},
        {"url": "https://new.example/", "markdown": "new page"},
    ]

    merged = merge_by_url(existing, incoming)

    assert merged == [
        {"url": "https://example.com/", "markdown": "new"},
        {"url": "https://keep.example/", "markdown": "keep"},
        {"url": "https://new.example/", "markdown": "new page"},
    ]
