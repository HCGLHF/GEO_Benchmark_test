import shlex

from scripts.ui_app import server
from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan


def test_build_run_plan_prefers_quick_parallel_seeded_flow() -> None:
    request = RunPlanRequest(
        platform="windows",
        own_site_url="https://alphaxxxx.com/",
        extra_site_urls=["https://docs.alphaxxxx.com/"],
        run_mode="quick",
        selected_models=["openai/gpt-4.1-mini", "google/gemini-2.5-flash"],
        recrawl_own_site=True,
        rescan_corpus=False,
        regenerate_scenarios=False,
        sync_aws=False,
        parallel_api=True,
        seed_queries_run_dir="runs/client_acquisition_simulator_full_api_20260517_200716",
    )

    plan = build_run_plan(request)

    assert plan.requires_api is True
    assert plan.requires_aws is False
    assert plan.estimated_queries_per_model == 50
    labels = [command.label for command in plan.commands]
    assert labels.count("Recrawl and fetch AlphaXXXX pages") == 1
    assert "Fetch AlphaXXXX pages" not in labels
    assert any("refresh_owned_site_crawl.py" in command.command for command in plan.commands)
    assert any("refresh_owned_site_processed.py" in command.command for command in plan.commands)
    assert any("--seed-url https://alphaxxxx.com/" in command.command for command in plan.commands)
    assert any("--seed-url https://docs.alphaxxxx.com/" in command.command for command in plan.commands)
    assert any("--stage owned_site_crawl" in command.command for command in plan.commands)
    assert any("scripts\\full_api_parallel_runner.py" in command.command for command in plan.commands)
    assert all("powershell" not in command.command.lower() for command in plan.commands)
    assert any("REM Reuse data\\processed and existing BM25 artifacts" == command.command for command in plan.commands)
    assert any("--run-mode quick" in command.command for command in plan.commands)
    assert any("--seed-queries-run-dir" in command.command for command in plan.commands)
    assert any("--models openai/gpt-4.1-mini,google/gemini-2.5-flash" in command.command for command in plan.commands)


def test_build_run_plan_includes_cloud_sync_when_requested() -> None:
    request = RunPlanRequest(
        platform="windows",
        run_mode="standard",
        selected_models=["openai/gpt-4.1-mini"],
        recrawl_own_site=False,
        rescan_corpus=True,
        regenerate_scenarios=True,
        sync_aws=True,
        parallel_api=False,
    )

    plan = build_run_plan(request)

    assert plan.requires_api is True
    assert plan.requires_aws is True
    assert plan.estimated_queries_per_model == 200
    assert any("build_keyword_index.py" in command.command for command in plan.commands)
    assert any("scripts\\cloud\\import_corpus.py" in command.command for command in plan.commands)
    assert any("--include-model" in command.command for command in plan.commands)


def test_build_run_plan_test_mode_keeps_api_calls_under_five_class() -> None:
    request = RunPlanRequest(
        platform="windows",
        run_mode="test",
        selected_models=["openai/gpt-4.1-mini"],
        recrawl_own_site=False,
        rescan_corpus=False,
        regenerate_scenarios=False,
        parallel_api=True,
        seed_queries_run_dir="runs/client_acquisition_simulator_full_api_20260517_200716",
    )

    plan = build_run_plan(request)

    assert plan.estimated_queries_per_model == 2
    assert plan.estimated_api_calls_per_model == 4
    assert any("--run-mode test" in command.command for command in plan.commands)
    assert any("--queries-per-model 2" in command.command for command in plan.commands)


def test_build_run_plan_warns_when_test_mode_regenerates_scenarios() -> None:
    request = RunPlanRequest(
        run_mode="test",
        regenerate_scenarios=True,
        parallel_api=True,
    )

    plan = build_run_plan(request)

    assert any("test mode" in warning.lower() and "scenario" in warning.lower() for warning in plan.warnings)


def test_build_run_plan_wsl_parallel_uses_posix_paths_and_preserves_api_args() -> None:
    request = RunPlanRequest(
        platform="wsl",
        own_site_url="https://alphaxxxx.com/",
        run_mode="quick",
        selected_models=["openai/gpt-4.1-mini", "bytedance-seed/seed-2.0-pro"],
        recrawl_own_site=True,
        rescan_corpus=False,
        regenerate_scenarios=False,
        parallel_api=True,
        seed_queries_run_dir="runs/client_acquisition_simulator_full_api_20260517_200716",
        api_run_root="runs/full_api_parallel_ui",
        run_stamp="20260526_120000",
    )

    plan = build_run_plan(request)
    commands = [command.command for command in plan.commands]
    api_command = next(command for command in commands if "full_api_parallel_runner.py" in command)

    assert "# Reuse data/processed and existing BM25 artifacts" in commands
    assert any(command.startswith("python scripts/run_pipeline_step.py") for command in commands)
    assert any("data/processed" in command for command in commands)
    assert all("\\" not in command for command in commands)
    assert "scripts/full_api_parallel_runner.py" in api_command
    assert "scripts\\full_api_parallel_runner.py" not in api_command
    assert "powershell" not in api_command.lower()
    assert "--platform wsl" in api_command
    assert "--models openai/gpt-4.1-mini,bytedance-seed/seed-2.0-pro" in api_command
    assert "--seed-queries-run-dir runs/client_acquisition_simulator_full_api_20260517_200716" in api_command
    assert "--include-doubao" in api_command
    assert "--run-stamp 20260526_120000" in api_command


def test_build_run_plan_quotes_tricky_seed_urls_for_wsl_nested_command() -> None:
    tricky_url = 'https://docs.alphaxxxx.com/path with spaces/?q=$deal&name="quoted"`tick'
    request = RunPlanRequest(
        platform="wsl",
        own_site_url=tricky_url,
        recrawl_own_site=True,
        rescan_corpus=False,
        parallel_api=False,
    )

    plan = build_run_plan(request)
    crawl_command = next(command.command for command in plan.commands if "refresh_owned_site_crawl.py" in command.command)

    assert f"--seed-url '{tricky_url}'" in crawl_command
    assert tricky_url in shlex.split(crawl_command)
    assert "&" not in shlex.split(crawl_command)
    assert "$deal" not in shlex.split(crawl_command)


def test_build_run_plan_quotes_tricky_seed_urls_for_windows_nested_command() -> None:
    tricky_url = 'https://docs.alphaxxxx.com/path with spaces/?q=$deal&name="quoted"`tick'
    request = RunPlanRequest(
        platform="windows",
        own_site_url=tricky_url,
        recrawl_own_site=True,
        rescan_corpus=False,
        parallel_api=False,
    )

    plan = build_run_plan(request)
    crawl_command = next(command.command for command in plan.commands if "refresh_owned_site_crawl.py" in command.command)

    assert f"--seed-url '{tricky_url}'" in crawl_command
    assert f'--seed-url "{tricky_url}"' not in crawl_command
    assert f"--seed-url {tricky_url}" not in crawl_command


def test_embedded_html_exposes_platform_control_and_collects_platform_param() -> None:
    assert 'id="platform"' in server.HTML
    assert '<option value="auto">auto</option>' in server.HTML
    assert '<option value="windows">windows</option>' in server.HTML
    assert '<option value="wsl">wsl</option>' in server.HTML
    assert '<option value="linux">linux</option>' in server.HTML
    assert 'params.set("platform", byId("platform").value);' in server.HTML


def test_embedded_html_normalizes_pipeline_step_filter_for_wsl_paths() -> None:
    assert 'replaceAll("\\\\", "/").startsWith("python scripts/run_pipeline_step.py")' in server.HTML
