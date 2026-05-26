import signal
from pathlib import Path

from scripts.ui_app.execution import launch_guarded_run, launch_guarded_stage, resume_guarded_run, stop_guarded_run
from scripts.ui_app.run_plan import RunPlanRequest


class FakeProcess:
    def __init__(self, pid: int = 4242):
        self.pid = pid


class FakeCompletedProcess:
    returncode = 0
    stdout = "SUCCESS"
    stderr = ""


def test_launch_guarded_run_requires_confirmation(tmp_path: Path) -> None:
    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(platform="windows", selected_models=["openai/gpt-4.1-mini"]),
        confirmed=False,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        stamp_factory=lambda: "20260522_120000",
    )

    assert result["status"] == "confirmation_required"
    assert "scripts\\full_api_parallel_runner.py" in result["command"]
    assert "--platform windows" in result["command"]
    assert not (tmp_path / "runs" / "ui_launches").exists()


def test_launch_guarded_run_starts_generated_api_command_and_writes_manifest(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(
            platform="windows",
            selected_models=["openai/gpt-4.1-mini", "deepseek/deepseek-chat"],
            seed_queries_run_dir="runs/seed",
        ),
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_120000",
    )

    assert result["status"] == "launched"
    assert result["pid"] == 4242
    assert result["platform"] == "windows"
    assert result["monitor_run_root"].endswith("runs/full_api_parallel_ui/20260522_120000")
    assert "--run-stamp 20260522_120000" in result["command"]
    assert "--models openai/gpt-4.1-mini,deepseek/deepseek-chat" in result["command"]
    assert (Path(result["launch_dir"]) / "launch_manifest.json").exists()
    assert calls[0][0][0][:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def test_launch_guarded_run_wsl_records_platform_group_and_uses_bash(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=5151)

    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(
            platform="wsl",
            selected_models=["openai/gpt-4.1-mini"],
            seed_queries_run_dir="runs/seed",
            api_run_root="runs/full_api_parallel_ui",
        ),
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_120000",
    )

    assert result["status"] == "launched"
    assert result["platform"] == "wsl"
    assert result["pid"] == 5151
    assert result["process_group_id"] == 5151
    assert "scripts/full_api_parallel_runner.py" in result["command"]
    assert "\\" not in result["command"]
    assert calls[0][0][0][:2] == ["bash", "-lc"]
    assert calls[0][1]["start_new_session"] is True

    manifest = Path(result["manifest_path"]).read_text(encoding="utf-8")
    assert '"platform": "wsl"' in manifest
    assert '"process_group_id": 5151' in manifest


def test_launch_guarded_stage_requires_confirmation_and_uses_generated_command(tmp_path: Path) -> None:
    result = launch_guarded_stage(
        project_root=tmp_path,
        request=RunPlanRequest(platform="windows", recrawl_own_site=True, selected_models=["openai/gpt-4.1-mini"]),
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
        request=RunPlanRequest(platform="windows", recrawl_own_site=True, selected_models=["openai/gpt-4.1-mini"]),
        command_label="Recrawl and fetch AlphaXXXX pages",
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_130000",
    )

    assert result["status"] == "launched"
    assert result["pid"] == 4242
    assert result["platform"] == "windows"
    assert result["command_label"] == "Recrawl and fetch AlphaXXXX pages"
    assert result["monitor_run_root"].endswith("runs/ui_pipeline/20260522_130000")
    assert (Path(result["launch_dir"]) / "launch_manifest.json").exists()
    assert calls


def test_launch_guarded_stage_accepts_wsl_slash_path_command(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=6161)

    result = launch_guarded_stage(
        project_root=tmp_path,
        request=RunPlanRequest(platform="wsl", recrawl_own_site=True, selected_models=["openai/gpt-4.1-mini"]),
        command_label="Recrawl and fetch AlphaXXXX pages",
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260522_130000",
    )

    assert result["status"] == "launched"
    assert result["platform"] == "wsl"
    assert result["process_group_id"] == 6161
    assert result["command"].startswith("python scripts/run_pipeline_step.py")
    assert calls[0][0][0][:2] == ["bash", "-lc"]


def test_stop_guarded_run_requires_confirmation_for_matching_api_launch(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "launched",
  "pid": 1234,
  "command": "powershell -ExecutionPolicy Bypass -File scripts\\\\run_full_api_parallel_with_watch.ps1 -RunRoot runs\\\\full_api_parallel_ui -RunStamp \\"20260525_010000\\"",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=False,
        process_runner=lambda *args, **kwargs: FakeCompletedProcess(),
    )

    assert result["status"] == "confirmation_required"
    assert result["pid"] == 1234
    assert "taskkill" in result["stop_command"]
    assert not (tmp_path / "runs" / "full_api_parallel_ui" / "20260525_010000" / "pipeline_state.jsonl").exists()


def test_stop_guarded_run_kills_process_tree_and_marks_run_interrupted(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "launched",
  "pid": 1234,
  "command": "powershell -ExecutionPolicy Bypass -File scripts\\\\run_full_api_parallel_with_watch.ps1 -RunRoot runs\\\\full_api_parallel_ui -RunStamp \\"20260525_010000\\"",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeCompletedProcess()

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=True,
        reason="402 Payment Required",
        process_runner=fake_runner,
    )

    assert result["status"] == "stopped"
    assert calls[0][0][0] == ["taskkill", "/PID", "1234", "/T", "/F"]
    state_path = tmp_path / "runs" / "full_api_parallel_ui" / "20260525_010000" / "pipeline_state.jsonl"
    assert "interrupted" in state_path.read_text(encoding="utf-8")
    updated_manifest = manifest.read_text(encoding="utf-8")
    assert '"status": "stopped"' in updated_manifest
    assert "402 Payment Required" in updated_manifest


def test_stop_guarded_run_wsl_uses_manifest_process_group(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "launched",
  "platform": "wsl",
  "pid": 1234,
  "process_group_id": 4321,
  "command": "python scripts/full_api_parallel_runner.py --run-root runs/full_api_parallel_ui --platform wsl",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )
    signals = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        signals.append((process_group_id, signal_number))

    preview = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=False,
        killpg=fake_killpg,
    )
    assert preview["status"] == "confirmation_required"
    assert preview["stop_command"] == "kill -- -4321"
    assert signals == []

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=True,
        killpg=fake_killpg,
    )

    assert result["status"] == "stopped"
    assert result["stop_command"] == "kill -- -4321"
    assert signals == [(4321, signal.SIGTERM)]
    updated_manifest = manifest.read_text(encoding="utf-8")
    assert '"stop_command": "kill -- -4321"' in updated_manifest


def test_stop_guarded_run_infers_wsl_platform_from_legacy_command(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "launched",
  "pid": 1234,
  "process_group_id": "",
  "command": "python scripts/full_api_parallel_runner.py --run-root runs/full_api_parallel_ui --platform wsl",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )
    signals = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        signals.append((process_group_id, signal_number))

    preview = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=False,
        killpg=fake_killpg,
    )

    assert preview["status"] == "confirmation_required"
    assert preview["platform"] == "wsl"
    assert preview["process_group_id"] is None
    assert preview["stop_command"] == "kill -- -1234"

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=True,
        killpg=fake_killpg,
    )

    assert result["status"] == "stopped"
    assert signals == [(1234, signal.SIGTERM)]


def test_stop_guarded_run_rejects_non_api_launch(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '{"status":"launched","pid":1234,"command":"python scripts\\\\run_pipeline_step.py","monitor_run_root":"runs/ui_pipeline/20260525_010000"}',
        encoding="utf-8",
    )

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/ui_pipeline/20260525_010000",
        confirmed=True,
        process_runner=lambda *args, **kwargs: FakeCompletedProcess(),
    )

    assert result["status"] == "rejected"
    assert "API benchmark launch" in result["error"]


def test_resume_guarded_run_reuses_original_api_command_and_monitor_root(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "stopped",
  "pid": 1234,
  "command": "powershell -ExecutionPolicy Bypass -File scripts\\\\run_full_api_parallel_with_watch.ps1 -RunRoot runs\\\\full_api_parallel_ui -RunStamp \\"20260525_010000\\"",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    result = resume_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260525_020000",
    )

    assert result["status"] == "launched"
    assert result["action"] == "resume"
    assert result["pid"] == 4242
    assert result["platform"] == "windows"
    assert result["monitor_run_root"] == "runs/full_api_parallel_ui/20260525_010000"
    assert "run_full_api_parallel_with_watch.ps1" in result["command"]
    assert (tmp_path / "runs" / "ui_launches" / "20260525_020000_resume" / "launch_manifest.json").exists()
    assert calls


def test_resume_guarded_run_preserves_wsl_platform_and_process_group(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260525_010000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """
{
  "status": "stopped",
  "platform": "wsl",
  "pid": 1234,
  "process_group_id": 1234,
  "command": "python scripts/full_api_parallel_runner.py --run-mode quick --run-root runs/full_api_parallel_ui --platform wsl --run-stamp 20260525_010000",
  "monitor_run_root": "runs/full_api_parallel_ui/20260525_010000"
}
""".strip(),
        encoding="utf-8",
    )
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=5252)

    result = resume_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260525_010000",
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260525_020000",
    )

    assert result["status"] == "launched"
    assert result["platform"] == "wsl"
    assert result["pid"] == 5252
    assert result["process_group_id"] == 5252
    assert result["monitor_run_root"] == "runs/full_api_parallel_ui/20260525_010000"
    assert calls[0][0][0][:2] == ["bash", "-lc"]
    resume_manifest = tmp_path / "runs" / "ui_launches" / "20260525_020000_resume" / "launch_manifest.json"
    assert '"platform": "wsl"' in resume_manifest.read_text(encoding="utf-8")
