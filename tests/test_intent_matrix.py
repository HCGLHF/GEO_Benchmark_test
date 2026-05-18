from pathlib import Path

from scripts.geo_eval.intent_matrix import load_intent_signal_matrix


def test_load_intent_signal_matrix_from_repo_config():
    matrix = load_intent_signal_matrix(Path("config/intent_signal_matrix.yaml"))

    assert matrix["version"] == "2026-05-16"
    assert "ai_recommendation_visibility" in matrix["intents"]
    assert "service_page" in matrix["page_types"]
    assert "trust_proof" in matrix["signals"]


def test_loader_rejects_missing_required_sections(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text('version: "x"\nintents: {}\n', encoding="utf-8")

    try:
        load_intent_signal_matrix(path)
    except ValueError as exc:
        assert "missing required matrix sections" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
