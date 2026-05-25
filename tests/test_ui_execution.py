from pathlib import Path

from scripts.ui_app.execution import launch_guarded_run, launch_guarded_stage
from scripts.ui_app.run_plan import RunPlanRequest


class FakeProcess:
    pid = 4242


def test_launch_guarded_run_requires_confirmation(tmp_path: Path) -> None:
    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(selected_models=["openai/gpt-4.1-mini"]),
        confirmed=False,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        stamp_factory=lambda: "20260522_120000",
    )

    assert result["status"] == "confirmation_required"
    assert "run_full_api_parallel_with_watch.ps1" in result["command"]
    assert not (tmp_path / "runs" / "ui_launches").exists()


def test_launch_guarded_run_starts_generated_api_command_and_writes_manifest(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(
            selected_models=["openai/gpt-4.1-mini", "deepseek/deepseek-chat"],
            seed_queries_run_dir="runs/seed",
        ),
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_120000",
    )

    assert result["status"] == "launched"
    assert result["pid"] == 4242
    assert result["monitor_run_root"].endswith("runs/full_api_parallel_ui/20260522_120000")
    assert "-RunStamp \"20260522_120000\"" in result["command"]
    assert "-Models \"openai/gpt-4.1-mini,deepseek/deepseek-chat\"" in result["command"]
    assert (Path(result["launch_dir"]) / "launch_manifest.json").exists()
    assert calls


def test_launch_guarded_stage_requires_confirmation_and_uses_generated_command(tmp_path: Path) -> None:
    result = launch_guarded_stage(
        project_root=tmp_path,
        request=RunPlanRequest(recrawl_own_site=True, selected_models=["openai/gpt-4.1-mini"]),
        command_label="Recrawl and fetch AlphaXXXX pages",
        confirmed=False,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        stamp_factory=lambda: "20260522_130000",
    )

    assert result["status"] == "confirmation_required"
    assert result["command_label"] == "Recrawl and fetch AlphaXXXX pages"
    assert result["command"].startswith("python scripts\\run_pipeline_step.py")
    assert "refresh_owned_site_crawl.py" in result["command"]
    assert "runs/ui_pipeline/20260522_130000" in result["monitor_run_root"]
    assert not (tmp_path / "runs" / "ui_launches").exists()


def test_launch_guarded_stage_rejects_api_or_placeholder_commands(tmp_path: Path) -> None:
    result = launch_guarded_stage(
        project_root=tmp_path,
        request=RunPlanRequest(recrawl_own_site=False, selected_models=["openai/gpt-4.1-mini"]),
        command_label="Run full API benchmark in parallel",
        confirmed=True,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        stamp_factory=lambda: "20260522_130000",
    )

    assert result["status"] == "rejected"
    assert "not a guarded pipeline step" in result["error"]


def test_launch_guarded_stage_starts_and_writes_manifest(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    result = launch_guarded_stage(
        project_root=tmp_path,
        request=RunPlanRequest(recrawl_own_site=True, selected_models=["openai/gpt-4.1-mini"]),
        command_label="Recrawl and fetch AlphaXXXX pages",
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_130000",
    )

    assert result["status"] == "launched"
    assert result["pid"] == 4242
    assert result["command_label"] == "Recrawl and fetch AlphaXXXX pages"
    assert result["monitor_run_root"].endswith("runs/ui_pipeline/20260522_130000")
    assert (Path(result["launch_dir"]) / "launch_manifest.json").exists()
    assert calls
