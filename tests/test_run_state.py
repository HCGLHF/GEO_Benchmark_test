from pathlib import Path

from scripts.geo_eval.run_state import RunState


def test_run_state_tracks_pending_complete_and_failed(tmp_path: Path):
    state = RunState(tmp_path / "run_state.sqlite")

    assert state.status("rerank", "q001", "model-a") == "pending"

    state.mark_complete("rerank", "q001", "model-a")
    assert state.status("rerank", "q001", "model-a") == "complete"

    state.mark_failed("answer", "q002", "model-a", "rate limited")
    assert state.status("answer", "q002", "model-a") == "failed"
    assert state.error("answer", "q002", "model-a") == "rate limited"
