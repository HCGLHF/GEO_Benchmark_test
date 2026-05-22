# Next

## Done

- Refreshed AlphaXXXX from the live site with the local crawler: discovered 37 URLs and crawled 37/37 successfully without Firecrawl.
- Replaced 32 old AlphaXXXX raw pages in the main resource library with 37 freshly crawled AlphaXXXX pages while preserving competitor pages.
- Rebuilt processed artifacts after the AlphaXXXX refresh: 1,683 documents, 6,225 chunks, 1,683 page signals, 1,683 evidence cards, and a refreshed BM25 index.
- Fixed quick seeded runs so `scripts\seed_api_queries.py` and `scripts\run_full_api_parallel_with_watch.ps1` cap copied seed questions to the effective `QueriesPerModel`.
- Fixed `generate_query_rows` so a seeded run with enough existing questions does not regenerate scenario questions just because the seed rows are not evenly distributed across persona/stage slots.
- Ran the refreshed AlphaXXXX quick API benchmark under `runs\full_api_parallel_alpha_refresh_quick_final\20260519_160422`.
- Completed and merged four quick model runs with 200 total queries, 200 retrieval rows, and 200 answer rows.
- Added `-RunMode quick|standard` to `scripts\run_full_api_parallel_with_watch.ps1`.
- Added the same `-RunMode quick|standard` behavior to the older `scripts\run_full_api_parallel.ps1` launcher for consistency.
- Changed the default parallel API run mode to `quick`, which uses 50 queries per model, roughly 100 seeded API calls per model.
- Kept the previous 200-query, roughly 400-seeded-call behavior available as `-RunMode standard`.
- Preserved manual `-QueriesPerModel` override for exact sample-size experiments.
- Added `scripts/alphaxxxx_llms_router.py` and generated `content\alphaxxxx\llms.txt` as an intent router for AI recommendation, GEO education, agency comparison, pricing, SaaS, local business, SEO agency, platform visibility, and audit/checklist intents.
- Added `scripts/build_corpus_variant.py` to create an isolated `without_llms` processed corpus under `data\experiments\without_llms\processed`.
- Generated `config\client_acquisition_simulator.without_llms.yaml` so full API benchmarks can run against the same resource library with `llms.txt` removed.
- Added `scripts/compare_llms_ab_reports.py` to compare with-`llms.txt` and without-`llms.txt` merged benchmark outputs for AlphaXXXX lift.
- Verified the without-`llms.txt` corpus has zero `/llms.txt` URLs in documents, chunks, page signals, and evidence cards.
- Added `scripts/render_full_api_progress_html.py`, a static auto-refreshing HTML dashboard for full API parallel run progress.
- Updated `scripts/run_full_api_parallel_with_watch.ps1` to print and refresh `progress.html` during monitored parallel runs.
- Fixed `watch_full_api_run.py` expected-call counts for seeded runs so reused `api_queries.csv` runs no longer show missing scenario-generation calls.
- Preflighted OpenRouter with tiny non-corpus calls after top-up; all configured models passed.
- Ran a seeded full API benchmark against the existing local resource library and old scenario set under `runs\full_api_parallel\20260518_214558`.
- Completed OpenAI, Gemini, and Perplexity runs with 200 retrieval rows and 200 answer rows each, zero API failures.
- Stopped the slow DeepSeek worker at 182/200 answers per user direction and excluded it from the merged report.
- Merged the three complete model runs into `runs\full_api_parallel\20260518_214558\merged_3_models`.
- Refreshed the AlphaXXXX site crawl into the main local resource library.
- Discovered and crawled 32 AlphaXXXX pages with the local `httpx` crawler; no Firecrawl fallback was needed.
- Rebuilt main `documents.jsonl`, `chunks.jsonl`, page signals, evidence cards, and BM25 index from 1,678 documents and 6,214 chunks.
- Verified the refreshed main corpus has `AlphaXXXX` metadata on 32 documents / 42 chunks and no blank brands.
- Added `scripts/seed_api_queries.py` to copy existing API-generated questions into single-model worker run directories without PowerShell CSV BOM issues.
- Added `-SeedQueriesRunDir` support to `scripts/run_full_api_parallel_with_watch.ps1` so refreshed-corpus runs can reuse the old 800 questions instead of regenerating scenarios.
- Tested seeded query copying, script-path CLI execution, and the parallel runner dry-run path.
- Attempted a full API run against the refreshed corpus; it reached OpenRouter but returned `402 Payment Required` mid-run, so no valid merged report was produced.
- Added resume support for interrupted full API simulator runs.
- Scenario generation now skips existing provider/model/persona/stage slots and continues query IDs from the highest existing `qNNN`.
- Rerank and answer stages now skip completed `provider + model + query_id` rows and only fill missing work.
- `watch_full_api_run.py` now reports missing retrieval rows, answer rows, and terminal calls.
- Added incremental output writing for full API simulator runs.
- Scenario queries/attempts, rerank metrics/evidence/attempts, and answer rows now stream to disk as each unit completes.
- Added interruption tests proving completed rows remain on disk when a later scenario, rerank, or answer call is interrupted.
- Added `scripts/run_full_api_parallel_with_watch.ps1` for one-command single-model parallel full API runs.
- Added `--cache-path` support to `scripts/run_full_api_client_acquisition.py` so parallel model workers can use independent SQLite caches.
- Documented the watched parallel run command in project memory and the parallel full API run guide.
- Added a read-only `scripts/watch_full_api_run.py` monitor for full API runs.
- Added tests for monitor aggregation, missing files, stalled runs, text formatting, and latest-run discovery.
- Verified the monitor against the existing `client_acquisition_simulator_full_api_20260517_200716` run.
- Prepared the monitor script, tests, architecture note, and plan for upload to the GitHub-backed publish repository.
- Synchronized the current source, tests, configuration, and architecture memory into the GitHub-backed `_publish/GEO_Benchmark_test` repository.
- Completed pre-push validation for the publish repository.
- Created project memory and architecture self-check files.
- Recorded the requirement to read memory, architecture, risk, next-step, and ADR files before future code changes.
- Added the first ADR for persistent project memory and architecture self-check.

## Learned

- The refreshed AlphaXXXX corpus now has 37 URLs and 53 chunks, up from the previous 32 URLs and 42 chunks.
- The quick refreshed-corpus report shows AlphaXXXX at 10.0% Retrieval Top5 share, 10.5% Retrieval Top10 share, best rank 1, and 5.5% model mention rate across 200 answers.
- The initial quick implementation still copied all 200 seeded questions per model; this was stopped mid-run and fixed.
- A second issue caused seeded runs to regenerate scenarios when seed rows were not balanced across persona/stage slots; this was also fixed before the final merged run.
- Quick seed capping by row order overrepresented the B2B SaaS founder slice in the final run, so the result is useful directionally but needs stratified seed sampling for better representativeness.
- Seeded full API benchmarks spend about two model calls per query: one rerank call and one answer call. So 50 queries per model is the practical quick target for roughly 100 API calls per model.
- `quick` mode is appropriate for ten-minute-class directional checks; `standard` mode should remain the comparison baseline when a result will drive content strategy.
- The current processed corpus contained 2 `/llms.txt` documents, 6 `/llms.txt` chunks, 2 page signals, and 2 evidence cards; removing them leaves 1,676 documents and 6,208 chunks.
- The `llms.txt` A/B setup should reuse the existing seeded API scenario run so the only intended variable is corpus routing, not question generation.
- The with-`llms.txt` run should use `config\client_acquisition_simulator.yaml`; the without-`llms.txt` control should use `config\client_acquisition_simulator.without_llms.yaml`.
- OpenRouter 402 errors disappeared after the user topped up credits; the earlier failure was account-credit related rather than prompt, corpus, or model configuration.
- For seeded refreshed-corpus benchmarks, `standard` mode does 400 calls per model: 200 rerank and 200 answer calls.
- DeepSeek completed rerank but was much slower in answer generation, reaching 182/200 answers before being stopped.
- The three-model merged report shows AlphaXXXX at 6.5% Retrieval Top5 share and 5.8% model mention rate across 600 successful answers.
- The previous full API run contains 800 reusable questions: 200 each for `openai/gpt-4.1-mini`, `google/gemini-2.5-flash`, `perplexity/sonar-pro`, and `deepseek/deepseek-chat`.
- Windows PowerShell `Export-Csv -Encoding UTF8` can write a BOM that Python reads as part of the first CSV field name, so seeded API query files should be written by Python with `encoding="utf-8"`.
- The first full API retry accidentally regenerated scenario questions because the seed helper import failed when executed as a script; this is now covered by a CLI test.
- OpenRouter returned `402 Payment Required` after partial rerank progress, which means current API balance/credit is the main blocker for a complete report.
- The active workspace root is not itself a git repository; the publishable repository is `_publish/GEO_Benchmark_test`.
- The GitHub CLI is not installed in this environment, so this publish uses direct `git` commands instead of a PR workflow.
- The existing full API run has complete orchestrator attempts, so the monitor can report exact 1660/1660 completion from existing artifacts.
- One-command parallel execution is safest when each model gets its own output directory, run-state SQLite, and LLM cache SQLite.
- Incremental writes make `watch_full_api_run.py` useful during active runs because row counts update before the whole stage finishes.
- Resume behavior now treats existing output rows as the source of truth for completed work.
- The project now has an explicit rule that every development task must preserve engineering memory, architecture boundaries, and next-step judgment.
- Full API realism remains operationally useful but must be run by the user locally when it sends corpus excerpts to third-party APIs.

## Risks

- The latest quick report should not be treated as a full persona-balanced benchmark because the 50 seeded queries per model were selected by file order.
- `quick` mode has higher variance than `standard`, so weak movement should not be overinterpreted from one quick run.
- If `llms.txt` receives most AlphaXXXX Top5 hits, the report may show routing success without proving the destination pages are strong enough.
- If the with/without A/B uses different generated questions, model sets, or query counts, the lift result is not trustworthy.
- `runs\full_api_parallel\20260518_214558\merged_3_models` excludes DeepSeek, so any model-level claims from that report cover OpenAI, Gemini, and Perplexity only.
- DeepSeek partial outputs remain useful for debugging latency, but should not be mixed into final benchmark metrics without a clear partial-run label.
- The invalid `20260518_211444` run should not be used for decision-making because it regenerated scenarios before the seed fix and later hit OpenRouter 402 failures.
- A complete refreshed-corpus benchmark needs a new run after OpenRouter balance is fixed, using `-SeedQueriesRunDir runs\client_acquisition_simulator_full_api_20260517_200716`.
- Publishing must continue to avoid local `.env`, `data/`, `runs/`, `reports/`, `output/`, and vector database artifacts.
- Direct push to `main` has less review ceremony than a PR, so each publish needs an explicit local audit.
- Future changes may accidentally skip this memory check unless it is treated as part of the normal development entry routine.
- Reusing an old output directory now resumes from existing rows; use a new output directory when a clean rerun is intended.
- The monitor reports from files that already exist; it still cannot see one currently in-flight API call before the runner writes an attempt row.
- Parallel API execution can hit provider rate limits faster than serial execution, so failed model workers should be inspected before merge.

## Next

1. Add stratified seed sampling for quick runs so 50 seeded questions per model cover personas and journey stages instead of taking the first 50 rows.
2. Compare `runs\full_api_parallel_alpha_refresh_quick_final\20260519_160422\merged` against the previous merged baseline to quantify AlphaXXXX movement after the site refresh.
3. Strengthen AlphaXXXX pages for the weakest models and intents, especially OpenAI, Gemini, Perplexity, problem-aware, and vendor-discovery queries.
