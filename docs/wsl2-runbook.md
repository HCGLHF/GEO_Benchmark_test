# WSL2 Runbook

## Storage Rule

Run long benchmark jobs from Linux storage, not from a Windows-mounted path:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/HCGLHF/GEO_Benchmark_test.git Resourcepool_Gen
cd ~/projects/Resourcepool_Gen
```

Do not run overnight jobs from `/mnt/d/GEO-ALPHA/Resourcepool_Gen`. That path crosses into Windows storage and can reintroduce locking, metadata, and process-control friction.

## Setup Check

```bash
python3 --version
git --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest tests/test_platform_runtime.py tests/test_full_api_parallel_runner.py tests/test_full_api_parallel_with_watch.py -q
```

## Dry Run

```bash
source .venv/bin/activate
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini --dry-run
```

## Minimal API Chain Check

Run this only when `.env` contains the intended API keys and credits are available. This consumes external model calls.

```bash
source .venv/bin/activate
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini
python scripts/ops_logs.py doctor --run-root runs/full_api_parallel/<run-stamp>
```

Use the actual run stamp printed by the runner when checking `ops_logs.py doctor`.

## Stop And Resume

When launched from the UI inside WSL, stop uses the launch manifest process-group metadata. Manual shell runs can be stopped with Ctrl+C from the same terminal. After a forced stop, run:

```bash
python scripts/ops_logs.py doctor --run-root runs/full_api_parallel/<run-stamp>
```

Resume uses existing output rows and run-state files as checkpoints. If a run was launched through the UI, use the UI resume control so the same run root and platform metadata are reused.

## Publish Branch

Use a clean WSL clone or publish repository and keep secrets and generated artifacts out of Git. Do not add `.env`, `data/`, `runs/`, `reports/`, `output/`, Qdrant/vector database directories, or cache directories such as `.pytest_cache/`, `__pycache__/`, and local LLM/API caches.

```bash
cd ~/projects/Resourcepool_Gen
git checkout -b codex/wsl2-primary-runtime

python -m pytest tests/test_platform_runtime.py tests/test_full_api_parallel_runner.py tests/test_full_api_parallel_with_watch.py -q
python -m pytest tests/test_ui_run_plan.py tests/test_ui_execution.py tests/test_ui_run_monitor.py -q
python -m pytest tests/test_ops_logging.py tests/test_ops_logs_cli.py tests/test_run_pipeline_step.py tests/test_full_api_run_status.py -q

git status --short
git add .env.example .gitignore CONTEXT.md README.md docs scripts sql tests pyproject.toml geo-resource-library-plan.md
git status --short
git commit -m "feat: add wsl2 primary runtime"
git push -u origin codex/wsl2-primary-runtime
```

Before committing, review `git status --short` and confirm only source, tests, docs, SQL, and non-secret config examples are staged.
