from pathlib import Path

from tests.test_watch_full_api_run import make_sample_run
from scripts.render_full_api_progress_html import render_progress_html, write_progress_html


def test_render_progress_html_shows_model_cards_and_auto_refresh(tmp_path: Path):
    openai_run = tmp_path / "openai_gpt-4.1-mini"
    deepseek_run = tmp_path / "deepseek_deepseek-chat"
    make_sample_run(openai_run)
    make_sample_run(deepseek_run)

    html = render_progress_html([openai_run, deepseek_run], title="Full API Progress")

    assert "<meta http-equiv=\"refresh\" content=\"30\">" in html
    assert "Full API Progress" in html
    assert "openai_gpt-4.1-mini" in html
    assert "deepseek_deepseek-chat" in html
    assert "80.0%" in html
    assert "rate limited" in html
    assert "Retrieval rows" in html
    assert "Answer rows" in html


def test_write_progress_html_creates_parent_directory(tmp_path: Path):
    run_dir = tmp_path / "runs" / "model-a"
    make_sample_run(run_dir)
    output = tmp_path / "dashboard" / "progress.html"

    write_progress_html([run_dir], output)

    assert output.exists()
    assert "model-a" in output.read_text(encoding="utf-8")
