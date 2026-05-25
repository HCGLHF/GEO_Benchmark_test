from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan


def test_build_run_plan_prefers_quick_parallel_seeded_flow() -> None:
    request = RunPlanRequest(
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
    assert any("--seed-url \"https://alphaxxxx.com/\"" in command.command for command in plan.commands)
    assert any("--seed-url \"https://docs.alphaxxxx.com/\"" in command.command for command in plan.commands)
    assert any("--stage \"owned_site_crawl\"" in command.command for command in plan.commands)
    assert any("run_full_api_parallel_with_watch.ps1" in command.command for command in plan.commands)
    assert any("-RunMode quick" in command.command for command in plan.commands)
    assert any("-SeedQueriesRunDir" in command.command for command in plan.commands)
    assert any("-Models \"openai/gpt-4.1-mini,google/gemini-2.5-flash\"" in command.command for command in plan.commands)


def test_build_run_plan_includes_cloud_sync_when_requested() -> None:
    request = RunPlanRequest(
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
    assert any("-RunMode test" in command.command for command in plan.commands)
    assert any("-QueriesPerModel 2" in command.command for command in plan.commands)


def test_build_run_plan_warns_when_test_mode_regenerates_scenarios() -> None:
    request = RunPlanRequest(
        run_mode="test",
        regenerate_scenarios=True,
        parallel_api=True,
    )

    plan = build_run_plan(request)

    assert any("test mode" in warning.lower() and "scenario" in warning.lower() for warning in plan.warnings)
