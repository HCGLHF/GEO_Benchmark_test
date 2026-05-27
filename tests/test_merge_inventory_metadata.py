from scripts.merge_inventory_metadata import merge_inventory_with_documents


def test_merge_inventory_with_documents_adds_existing_document_metadata():
    inventory = [
        {
            "url": "https://new.example/",
            "brand": "New",
            "source_type": "official_site",
            "source_group": "own_site",
            "seed_url": "https://new.example/",
            "discovery_method": "manual_seed",
            "depth": "0",
            "status": "discovered",
        }
    ]
    documents = [
        {
            "url": "https://old.example/",
            "brand": "Old",
            "source_type": "industry_platform",
        }
    ]

    merged = merge_inventory_with_documents(inventory, documents)

    assert [row["url"] for row in merged] == ["https://new.example/", "https://old.example/"]
    assert merged[1]["brand"] == "Old"
    assert merged[1]["source_group"] == "existing_documents"
