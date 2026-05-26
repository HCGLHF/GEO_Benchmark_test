# Risks

## Current Risks

- AlphaXXXX has a very small corpus footprint compared with leading competitors, which suppresses recall before answer generation can help.
- Full external API evaluation can export retrieved corpus excerpts; Codex tool execution is restricted, so the user must run that path locally.
- Current full API flow now streams scenario, rerank, and answer rows incrementally, and writes API call events when calls start, finish, hit cache, or fail. Terminal progress should still be based on completed attempts so in-flight calls are not double-counted.
- Resume support skips already-streamed scenario slots, rerank rows, and answer rows, but stale output files in a reused run directory can intentionally suppress reruns.
- Parallel model runs need careful merging to avoid miscounting brand metrics or duplicating rows.
- Parallel model runs can now merge with model warnings when every expected query, retrieval, and answer row exists. Treat warning models as usable but caveated, and keep their API failure counts visible in reports.
- Doubao Pro on OpenRouter may fail because the requested model id has previously returned errors.
- OpenRouter can return `402 Payment Required` mid-run; partial retrieval rows may be written, but answer-stage metrics are not reliable until the account has enough balance for the whole run.
- Seeded reruns must verify that `api_queries.csv` was actually copied before workers start; otherwise the simulator will regenerate scenarios and invalidate a "same questions, refreshed corpus" comparison.
- DeepSeek can lag far behind the other models; partial DeepSeek output should not be merged into the main benchmark unless all 200 answers complete.
- `llms.txt` can inflate AlphaXXXX retrieval if it is the only strong matching page; evaluate both with and without `llms.txt` to separate routing benefit from page-level content strength.
- Corpus variants can become misleading if they overwrite the main processed artifacts or use different scenario questions.
- The new local UI is currently a dry-run planner. Treat generated commands as reviewable plans, not proof that a run has executed.

## Architecture Drift Signals

- Crawler scripts gaining evaluator-specific logic.
- Evaluator scripts directly manipulating raw crawler outputs instead of processed contracts.
- New helper files that contain unrelated crawling, indexing, API, and reporting logic together.
- Report metrics being patched manually instead of tested through aggregation functions.

## Operational Risks

- Large raw page files are expensive to copy and should not be used as the primary downstream input when `documents.jsonl` or `chunks.jsonl` is enough.
- Paid fallback usage should remain traceable by URL, reason, provider, and quality score.
- API concurrency can increase rate limits, timeout, and partial-output risks; streaming writes reduce data loss but do not replace retry/backoff controls.
- Parallel full API runs should use per-model cache files to avoid SQLite lock contention and preserve model-level independence.
- For a fully fresh benchmark, use a new output directory or delete the old run directory outside Codex after confirming no results need to be preserved.
- After force-stopping an invalid worker, check for child `python.exe` processes as well as the PowerShell wrapper because the child can continue consuming API calls.
- If the parent monitoring process times out, child model workers may continue. Inspect process command lines and per-model watcher output before deciding whether to stop or merge.
- With/without `llms.txt` A/B runs should use the same seed query run, the same model set, and the same query count; otherwise the measured lift mixes retrieval-routing effects with scenario variance.
- `quick` API runs trade statistical stability for speed. Use them to catch directional movement and broken changes, then confirm important decisions with `standard` runs.
- Quick seeded runs currently cap the existing query file by row order. If the original seed file is grouped by persona or journey stage, a quick run can overrepresent one scenario slice; use the result directionally until stratified seed sampling is added.
- `test` mode is only a chain diagnostic. Its two seeded queries per model are intentionally too small for ranking, recall, mention-rate, or content-strategy conclusions.
- The initial cloud-import dry run now blocks on 4 replacement-character rows after removing false positives from valid French accents. Importing with `--allow-quality-issues` is possible, but those rows should be reviewed or refreshed before treating the cloud corpus as clean.
- RDS is currently reachable from the user's local machine for setup. Keep the security group restricted to the user's current `/32` IP or move future imports behind EC2/SSM/VPN.
- Cloud import scripts require `boto3` and `psycopg[binary]` only when executing S3/RDS writes; these are installed project-locally under `.deps/cloud`, while local tests intentionally avoid live AWS dependencies.
- The first RDS import and S3 artifact upload succeeded, and the locally configured AWS credentials now use an IAM user key. The old root access key has been deactivated and should be deleted after one more successful IAM-key project run.
- Publishing database documentation is acceptable only while it contains identifiers and placeholders, not passwords, access keys, secret keys, private connection strings, exported database dumps, or local `.env` values.
- Remote team access depends on both IAM permissions for S3 and network/database permissions for RDS; Git access alone is not enough to run cloud-backed workflows.
- Qdrant snapshots in S3 are convenience restore artifacts, not authoritative data. A stale snapshot must not override a newer `chunks.jsonl` corpus version.
- Industry isolation is now enforced in cloud scripts, but any ad hoc SQL queries must still include `industry_id`; omitting it can mix unrelated industry datasets in analysis.
- The industry registry command creates metadata, not access control. IAM permissions, PostgreSQL roles, and RDS network allowlists still need to be managed separately for each teammate or role.
- The current `geo-agency` corpus has both legacy root-level S3 artifact keys and new `industries/geo-agency/...` keys registered. New tools should prefer the industry-prefixed keys.
- UI-selected arbitrary model subsets are now supported by the monitored parallel runner through `-Models`, but the selected model ids still must exist in the simulator config.
- Run Monitor now exposes guarded stop/resume for UI-launched API benchmarks by resolving the prior launch manifest and using `taskkill /T /F` on the recorded wrapper pid.
- WSL2 reduces Windows file-lock and process-tree issues only when jobs run from Linux filesystem storage such as `~/projects/Resourcepool_Gen`; running from `/mnt/d/GEO-ALPHA/Resourcepool_Gen` can reintroduce Windows metadata and locking friction.
- Stop/resume now depends on launch manifest platform metadata. If a launch manifest is edited manually, process-group stop can target the wrong process group.
- Pipeline stage visibility now depends on scripts using `pipeline_state.py` directly or being launched through `run_pipeline_step.py`; legacy/manual commands will remain invisible to stage-level monitor views.
- The UI can now launch the generated API benchmark command after confirmation. This is intentional and user-triggered, but it can consume OpenRouter/API credits.
- The UI can now launch generated `run_pipeline_step.py` commands after confirmation. These can mutate local raw/processed data or write to AWS if the selected stage does so.
- Launch manifests record the parent PowerShell process id. Stop uses Windows process-tree termination, but detached child processes should still be checked if API calls continue after a stop.
- Worker exit-code files can briefly exist empty at process shutdown on Windows. The parallel runner now waits for non-empty exit-code content before deciding whether a worker failed.
- `ops_summary.json` is interpretation, not benchmark truth; if it conflicts with underlying files, inspect `pipeline_state.jsonl`, worker exits, API attempts/events, and output artifacts.
- Local operations logs are stored inside run roots; deleting a run root deletes troubleshooting history, so archive important reports/logs before cleanup.
- Report history is file-mtime based and local-only. If old run artifacts are copied or edited manually, their order can change without implying a new benchmark was actually executed.
- Report preview is intentionally restricted to known completed report directories under `runs/`; adding broader file browsing would risk exposing local secrets or raw corpus files in the browser.
- Owned-page weak lists are retrieval-outcome signals, not absolute SEO/page-quality scores. A page can be marked weak because the sampled questions did not match its intent, especially in `test` mode.
- Report diagnostics now group query losses, competitor displacement URLs, and owned-page prescriptions, but their "why it won" signals are keyword-derived from retrieved titles/previews. Treat them as strong debugging clues, not causal proof.
- Page optimization priorities are based on retrieval outcomes and URL intent heuristics. A `P0` page still needs human editorial judgment before site changes are made.
