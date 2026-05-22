# Risks

## Current Risks

- AlphaXXXX has a very small corpus footprint compared with leading competitors, which suppresses recall before answer generation can help.
- Full external API evaluation can export retrieved corpus excerpts; Codex tool execution is restricted, so the user must run that path locally.
- Current full API flow now streams scenario, rerank, and answer rows incrementally, but a single in-flight API call is still invisible until the call returns or fails.
- Resume support skips already-streamed scenario slots, rerank rows, and answer rows, but stale output files in a reused run directory can intentionally suppress reruns.
- Parallel model runs need careful merging to avoid miscounting brand metrics or duplicating rows.
- Doubao Pro on OpenRouter may fail because the requested model id has previously returned errors.
- OpenRouter can return `402 Payment Required` mid-run; partial retrieval rows may be written, but answer-stage metrics are not reliable until the account has enough balance for the whole run.
- Seeded reruns must verify that `api_queries.csv` was actually copied before workers start; otherwise the simulator will regenerate scenarios and invalidate a "same questions, refreshed corpus" comparison.
- DeepSeek can lag far behind the other models; partial DeepSeek output should not be merged into the main benchmark unless all 200 answers complete.
- `llms.txt` can inflate AlphaXXXX retrieval if it is the only strong matching page; evaluate both with and without `llms.txt` to separate routing benefit from page-level content strength.
- Corpus variants can become misleading if they overwrite the main processed artifacts or use different scenario questions.

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
