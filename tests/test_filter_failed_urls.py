from scripts.filter_failed_urls import filter_failed_rows


def test_filter_failed_rows_keeps_inventory_rows_with_failed_logs():
    inventory = [
        {"url": "https://ok.example/", "brand": "OK"},
        {"url": "https://failed.example/", "brand": "Failed"},
    ]
    logs = [
        {"url": "https://ok.example/", "status": "success"},
        {"url": "https://failed.example/", "status": "failed"},
    ]

    failed = filter_failed_rows(inventory, logs)

    assert failed == [{"url": "https://failed.example/", "brand": "Failed"}]
