from scripts.cloud.verify_cloud_import import build_verification_result


def test_build_verification_result_passes_when_counts_and_artifacts_match():
    result = build_verification_result(
        corpus_version="2026-05-22-initial",
        expected_counts={
            "inventory_rows": 1683,
            "documents": 1683,
            "chunks": 6225,
            "artifacts": 3,
        },
        db_counts={
            "inventory_rows": 1683,
            "documents": 1683,
            "chunks": 6225,
            "artifacts": 3,
        },
        artifact_checks=[
            {
                "object_key": "raw/2026-05-22-initial/url_inventory.csv",
                "expected_size": 328092,
                "actual_size": 328092,
            }
        ],
    )

    assert result["ok"] is True
    assert result["failures"] == []


def test_build_verification_result_reports_count_and_artifact_mismatches():
    result = build_verification_result(
        corpus_version="2026-05-22-initial",
        expected_counts={
            "inventory_rows": 1683,
            "documents": 1683,
            "chunks": 6225,
            "artifacts": 3,
        },
        db_counts={
            "inventory_rows": 1683,
            "documents": 1682,
            "chunks": 6225,
            "artifacts": 3,
        },
        artifact_checks=[
            {
                "object_key": "processed/2026-05-22-initial/documents.jsonl",
                "expected_size": 10,
                "actual_size": 9,
            }
        ],
    )

    assert result["ok"] is False
    assert "documents expected 1683 but found 1682" in result["failures"]
    assert "processed/2026-05-22-initial/documents.jsonl expected 10 bytes but found 9" in result["failures"]
