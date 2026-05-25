from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunPlanRequest:
    own_site_url: str = "https://alphaxxxx.com/"
    extra_site_urls: list[str] = field(default_factory=list)
    run_mode: str = "quick"
    selected_models: list[str] = field(default_factory=list)
    recrawl_own_site: bool = True
    rescan_corpus: bool = False
    regenerate_scenarios: bool = False
    sync_aws: bool = False
    parallel_api: bool = True
    seed_queries_run_dir: str = ""
    custom_queries_per_model: int | None = None
    pipeline_run_root: str = "<run-root>"
    api_run_root: str = "runs\\full_api_parallel_ui"
    run_stamp: str = ""


@dataclass(frozen=True)
class PlannedCommand:
    label: str
    command: str
    note: str


@dataclass(frozen=True)
class RunPlan:
    commands: list[PlannedCommand]
    warnings: list[str]
    requires_api: bool
    requires_aws: bool
    estimated_queries_per_model: int
    estimated_api_calls_per_model: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _queries_for_mode(request: RunPlanRequest) -> int:
    if request.custom_queries_per_model:
        return request.custom_queries_per_model
    if request.run_mode == "test":
        return 2
    if request.run_mode == "standard":
        return 200
    return 50


def _pipeline_step(request: RunPlanRequest, stage: str, command: str) -> str:
    return f"python scripts\\run_pipeline_step.py --run-root {request.pipeline_run_root} --stage {_quote(stage)} -- {command}"


def build_run_plan(request: RunPlanRequest) -> RunPlan:
    commands: list[PlannedCommand] = []
    warnings: list[str] = []
    queries_per_model = _queries_for_mode(request)

    if request.recrawl_own_site:
        urls = [request.own_site_url] + [url for url in request.extra_site_urls if url.strip()]
        url_args = " ".join(f"--seed-url {_quote(url)}" for url in urls)
        commands.append(
            PlannedCommand(
                label="Recrawl and fetch AlphaXXXX pages",
                command=_pipeline_step(
                    request,
                    "owned_site_crawl",
                    "python scripts\\refresh_owned_site_crawl.py "
                    "--brand AlphaXXXX "
                    f"{url_args} "
                    "--discovered-output data\\raw\\alpha_update_discovered_urls.csv "
                    "--pages-output data\\raw\\alpha_update_pages.jsonl "
                    "--attempts-output data\\raw\\alpha_update_fetch_attempts.jsonl "
                    "--logs-output data\\raw\\alpha_update_crawl_logs.csv "
                    "--disable-paid-fallback",
                ),
                note="Discover current owned-site URLs and fetch those pages in one monitored step using the local crawler first.",
            )
        )
        commands.append(
            PlannedCommand(
                label="Refresh AlphaXXXX processed corpus and index",
                command=_pipeline_step(
                    request,
                    "clean",
                    "python scripts\\refresh_owned_site_processed.py "
                    "--raw-pages data\\raw\\alpha_update_pages.jsonl "
                    "--url-inventory data\\raw\\alpha_update_discovered_urls.csv "
                    "--processed-dir data\\processed "
                    "--target-domain alphaxxxx.com",
                ),
                note="Replace the old AlphaXXXX processed documents with the latest crawl, then rebuild chunks, signals, evidence cards, and BM25.",
            )
        )

    if request.rescan_corpus:
        commands.extend(
            [
                PlannedCommand(
                    label="Clean documents",
                    command=_pipeline_step(request, "clean", "python scripts\\clean_documents.py"),
                    note="Rebuild normalized documents from raw crawled pages.",
                ),
                PlannedCommand(
                    label="Chunk documents",
                    command=_pipeline_step(request, "chunk", "python scripts\\chunk_documents.py"),
                    note="Recreate retrieval chunks after document changes.",
                ),
                PlannedCommand(
                    label="Build keyword index",
                    command=_pipeline_step(request, "index", "python scripts\\build_keyword_index.py"),
                    note="Refresh BM25 so retrieval uses the current resource library.",
                ),
            ]
        )
    else:
        commands.append(
            PlannedCommand(
                label="Reuse existing resource library",
                command="REM Reuse data\\processed and existing BM25 artifacts",
                note="No full corpus rescan requested.",
            )
        )

    if request.sync_aws:
        commands.append(
            PlannedCommand(
                label="Sync corpus to AWS",
                command=_pipeline_step(
                    request,
                    "AWS sync",
                    "python scripts\\cloud\\import_corpus.py --industry geo-agency --corpus-version <new-corpus-version>",
                ),
                note="Requires AWS and PostgreSQL environment variables; writes processed artifacts to S3/RDS.",
            )
        )
        commands.append(
            PlannedCommand(
                label="Verify AWS import",
                command=_pipeline_step(
                    request,
                    "AWS sync",
                    "python scripts\\cloud\\verify_cloud_import.py --industry geo-agency --corpus-version <new-corpus-version>",
                ),
                note="Confirm RDS/S3 artifact counts before sharing the corpus with other machines.",
            )
        )

    if request.parallel_api:
        command = (
            "powershell -ExecutionPolicy Bypass -File scripts\\run_full_api_parallel_with_watch.ps1 "
            f"-RunMode {request.run_mode} "
            f"-QueriesPerModel {queries_per_model} "
            f"-RunRoot {request.api_run_root}"
        )
        if request.run_stamp:
            command += f" -RunStamp {_quote(request.run_stamp)}"
        if request.seed_queries_run_dir and not request.regenerate_scenarios:
            command += f" -SeedQueriesRunDir {_quote(request.seed_queries_run_dir)}"
        if any(model == "bytedance-seed/seed-2.0-pro" for model in request.selected_models):
            command += " -IncludeDoubao"
        if request.selected_models:
            command += " -Models " + _quote(",".join(request.selected_models))
        commands.append(
            PlannedCommand(
                label="Run full API benchmark in parallel",
                command=command,
                note="Runs one PowerShell worker per model and renders progress.html while the benchmark is active.",
            )
        )
    else:
        for model in request.selected_models or ["openai/gpt-4.1-mini"]:
            commands.append(
                PlannedCommand(
                    label=f"Run API benchmark: {model}",
                    command=(
                        "python scripts\\run_full_api_client_acquisition.py "
                        "--config config\\client_acquisition_simulator.yaml "
                        f"--include-model {_quote(model)} "
                        f"--queries-per-model {queries_per_model}"
                    ),
                    note="Serial single-model run; useful for isolating one provider before merging.",
                )
            )

    if request.regenerate_scenarios:
        warnings.append("Scenario regeneration is enabled, so this run will not be directly comparable with seeded historical runs.")
        if request.run_mode == "test":
            warnings.append("Test mode is only a minimal API-chain check when it reuses seeded scenarios; regenerating scenarios adds extra API calls.")
    elif not request.seed_queries_run_dir:
        warnings.append("No seed query run was selected. Add one when you want model-to-model comparisons against the existing scenario set.")

    return RunPlan(
        commands=commands,
        warnings=warnings,
        requires_api=True,
        requires_aws=request.sync_aws,
        estimated_queries_per_model=queries_per_model,
        estimated_api_calls_per_model=queries_per_model * 2,
    )
