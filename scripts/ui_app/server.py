from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts.ui_app.dashboard import build_dashboard_state
from scripts.ui_app.execution import launch_guarded_run, launch_guarded_stage, resume_guarded_run, stop_guarded_run
from scripts.ui_app.page_drilldown_summary import summarize_report_page_drilldown
from scripts.ui_app.report_history import list_report_history, read_report_preview
from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan
from scripts.ui_app.run_monitor import summarize_parallel_run


PROJECT_ROOT = Path(__file__).resolve().parents[2]


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GEO Benchmark Console</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --surface: #f6f7f9;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-weak: #d9f4ef;
      --warn: #9a3412;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--surface);
    }
    header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { font-size: 20px; margin: 0; letter-spacing: 0; }
    h2 { font-size: 15px; margin: 0 0 12px; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 460px) minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      align-items: start;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
      overflow: hidden;
    }
    .stack { display: grid; gap: 16px; min-width: 0; align-content: start; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 74px;
      background: #fbfcfe;
    }
    .metric strong { display: block; font-size: 24px; line-height: 1.2; }
    .metric span, label, .muted { color: var(--muted); font-size: 13px; }
    .row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    input[type="text"], input[type="number"], textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: white;
      min-height: 38px;
    }
    textarea { min-height: 76px; resize: vertical; }
    .checks {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 12px;
      margin-top: 8px;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfe;
    }
    .button {
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
    }
    .button.secondary {
      background: #344054;
    }
    .button.inline {
      padding: 6px 9px;
      font-size: 12px;
    }
    .list {
      display: grid;
      gap: 6px;
      max-height: 260px;
      overflow: auto;
      padding-right: 4px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      background: #fbfcfe;
      margin: 0 6px 6px 0;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: anywhere;
      background: #111827;
      color: #e5e7eb;
      border-radius: 8px;
      padding: 12px;
      min-height: 170px;
      max-width: 100%;
      overflow: auto;
      font-size: 12px;
      line-height: 1.5;
      font-family: "Cascadia Mono", Consolas, "Liberation Mono", monospace;
      letter-spacing: 0;
    }
    .warning {
      color: var(--warn);
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 6px;
      padding: 10px;
      margin-top: 10px;
      font-size: 13px;
    }
    .progress-cell {
      min-width: 160px;
    }
    .progress-track {
      height: 8px;
      width: 100%;
      border-radius: 999px;
      background: #e5e7eb;
      overflow: hidden;
      margin-top: 4px;
    }
    .progress-fill {
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
      transition: width 160ms ease;
    }
    .progress-label {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .table-scroll {
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      padding-bottom: 2px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    td, th { border-bottom: 1px solid var(--line); text-align: left; padding: 8px 6px; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    .owned-pages-table {
      table-layout: fixed;
      min-width: 720px;
    }
    .owned-pages-table th,
    .owned-pages-table td {
      padding: 9px 8px;
      line-height: 1.35;
    }
    .url-cell {
      overflow-wrap: anywhere;
      word-break: normal;
    }
    .metric-cell {
      width: 82px;
      white-space: nowrap;
    }
    .hint-cell {
      overflow-wrap: break-word;
      word-break: normal;
    }
    @media (max-width: 920px) {
      main { grid-template-columns: 1fr; }
      .row, .checks { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>GEO Benchmark Console</h1>
    <button class="button secondary" id="refresh">Refresh</button>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>Resource Library</h2>
        <div class="metrics">
          <div class="metric"><strong id="companyCount">0</strong><span>companies</span></div>
          <div class="metric"><strong id="urlCount">0</strong><span>URLs</span></div>
          <div class="metric"><strong id="documentCount">0</strong><span>documents</span></div>
          <div class="metric"><strong id="chunkCount">0</strong><span>chunks</span></div>
        </div>
      </section>
      <section>
        <h2>Latest Report</h2>
        <div class="metrics">
          <div class="metric"><strong id="targetRank">-</strong><span>AlphaXXXX rank</span></div>
          <div class="metric"><strong id="targetTop5">-</strong><span>Retrieval Top5</span></div>
          <div class="metric"><strong id="targetMention">-</strong><span>Model mention</span></div>
          <div class="metric"><strong id="answerCount">-</strong><span>answers</span></div>
        </div>
        <div id="reportPath" class="muted" style="margin-top:10px;"></div>
      </section>
      <section>
        <h2>Report History</h2>
        <div id="reportHistoryTable" class="muted">No report history loaded</div>
      </section>
      <section>
        <h2>Report Preview</h2>
        <pre id="reportPreview">(select a report)</pre>
      </section>
      <section>
        <h2>Owned Page Drilldown</h2>
        <div id="ownedPageSource" class="muted">Select or load a report</div>
        <h2 style="margin-top:14px;">Top5 Retrieved Pages</h2>
        <div id="ownedTopPagesTable" class="muted">No report loaded</div>
        <h2 style="margin-top:14px;">Weak Pages To Optimize</h2>
        <div id="ownedWeakPagesTable" class="muted">No report loaded</div>
      </section>
      <section>
        <h2>Cloud Store</h2>
        <table>
          <tbody id="cloudRows"></tbody>
        </table>
      </section>
    </div>
    <div class="stack">
      <section>
        <h2>Run Setup</h2>
        <div class="row">
          <label>Main site
            <input id="ownSiteUrl" type="text" value="https://alphaxxxx.com/">
          </label>
          <label>Run mode
            <select id="runMode">
              <option value="test">test</option>
              <option value="quick">quick</option>
              <option value="standard">standard</option>
              <option value="custom">custom</option>
            </select>
          </label>
        </div>
        <div class="row" style="margin-top:12px;">
          <label>Pipeline run root
            <input id="pipelineRunRoot" type="text" value="runs/ui_pipeline/<timestamp>">
          </label>
          <label>Monitor run root
            <input id="linkedMonitorRoot" type="text" value="runs/full_api_parallel_alpha_refresh_quick_final/20260519_160422">
          </label>
        </div>
        <div class="row" style="margin-top:12px;">
          <label>Extra owned URLs
            <textarea id="extraSiteUrls"></textarea>
          </label>
          <label>Seed query run
            <input id="seedQueriesRunDir" type="text" value="runs/client_acquisition_simulator_full_api_20260517_200716">
          </label>
        </div>
        <div class="checks">
          <label class="check"><input id="recrawlOwnSite" type="checkbox" checked> Recrawl owned site</label>
          <label class="check"><input id="rescanCorpus" type="checkbox"> Rescan full corpus</label>
          <label class="check"><input id="regenerateScenarios" type="checkbox"> Regenerate scenarios</label>
          <label class="check"><input id="syncAws" type="checkbox"> Sync AWS</label>
          <label class="check"><input id="parallelApi" type="checkbox" checked> Parallel API</label>
          <label class="check">Custom queries <input id="customQueries" type="number" min="1" value=""></label>
        </div>
        <h2 style="margin-top:16px;">Models</h2>
        <div class="list" id="modelList"></div>
        <div style="margin-top:12px;">
          <button class="button" id="plan">Build Run Plan</button>
          <button class="button secondary" id="launchApi">Launch API Run</button>
        </div>
        <div class="row" style="margin-top:12px;">
          <label>Pipeline step
            <select id="stageCommand"></select>
          </label>
          <label>Step launch
            <button class="button secondary" id="launchStage" type="button">Launch Step</button>
          </label>
        </div>
        <div id="launchStatus" class="muted" style="margin-top:10px;"></div>
      </section>
      <section>
        <h2>Competitors</h2>
        <div id="competitors"></div>
      </section>
      <section>
        <h2>Dry Run Commands</h2>
        <pre id="commands"></pre>
        <div id="warnings"></div>
      </section>
      <section>
        <h2>Run Monitor</h2>
        <div class="row">
          <label>Parallel run root
            <input id="monitorRunRoot" type="text" value="runs/full_api_parallel_alpha_refresh_quick_final/20260519_160422">
          </label>
          <label>Current stage
            <input id="monitorStage" type="text" readonly>
          </label>
        </div>
        <div class="metrics" style="margin-top:12px;">
          <div class="metric"><strong id="monitorApiCalls">-</strong><span>API calls</span></div>
          <div class="metric"><strong id="monitorFailures">-</strong><span>failures</span></div>
          <div class="metric"><strong id="monitorProgress">-</strong><span>terminal progress</span></div>
          <div class="metric"><strong id="monitorModels">-</strong><span>model workers</span></div>
          <div class="metric"><strong id="monitorHealth">-</strong><span>chain health</span></div>
        </div>
        <div style="margin-top:12px;">
          <button class="button secondary" id="monitorRefresh">Refresh Monitor</button>
          <button class="button secondary" id="stopApiRun">Stop API Run</button>
          <button class="button" id="resumeApiRun">Resume API Run</button>
          <label class="check" style="display:inline-flex; margin-left:8px; width:auto;">
            <input id="monitorAutoRefresh" type="checkbox" checked> Auto-refresh
          </label>
        </div>
        <div id="monitorModelsTable" style="margin-top:12px;"></div>
        <div id="monitorStagesTable" style="margin-top:12px;"></div>
        <pre id="monitorLog"></pre>
      </section>
    </div>
  </main>
  <script>
    let state = null;
    let lastPlan = null;

    const byId = (id) => document.getElementById(id);
    const monitorStorageKey = "geo.monitorRunRoot";
    const percent = (value) => value === null || value === undefined ? "-" : `${Number(value).toFixed(1)}%`;
    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

    async function loadState() {
      const response = await fetch("/api/state");
      state = await response.json();
      const corpus = state.corpus;
      byId("companyCount").textContent = corpus.company_count;
      byId("urlCount").textContent = corpus.url_count;
      byId("documentCount").textContent = corpus.document_count;
      byId("chunkCount").textContent = corpus.chunk_count;

      const report = state.report;
      byId("targetRank").textContent = report.target_rank_by_top5 || "-";
      byId("targetTop5").textContent = percent(report.target_top5_share);
      byId("targetMention").textContent = percent(report.target_model_mention_rate);
      byId("answerCount").textContent = report.answer_count || "-";
      byId("reportPath").textContent = report.report_dir || "No merged report found";

      byId("ownSiteUrl").value = state.options.default_own_site_url;
      renderModels(state.options.models);
      renderCompetitors(state.options.competitors, report.brands_above_target);
      renderCloud(state.cloud);
      renderReportHistory(state.report_history || []);
      if (report.report_dir) await loadPageDrilldown(report.report_dir);
      const restoredMonitorRoot = state.latest_monitor_run_root || localStorage.getItem(monitorStorageKey) || "";
      if (restoredMonitorRoot) setMonitorRunRoot(restoredMonitorRoot, true);
      await buildPlan();
    }

    function setMonitorRunRoot(runRoot, persist = true) {
      if (!runRoot) return;
      byId("monitorRunRoot").value = runRoot;
      byId("linkedMonitorRoot").value = runRoot;
      if (persist) localStorage.setItem(monitorStorageKey, runRoot);
    }

    function renderLatestReport(report) {
      if (!report || !report.report_dir) return;
      byId("targetRank").textContent = report.target_rank_by_top5 || "-";
      byId("targetTop5").textContent = percent(report.target_top5_share);
      byId("targetMention").textContent = percent(report.target_model_mention_rate);
      byId("answerCount").textContent = report.answer_count || "-";
      byId("reportPath").textContent = report.report_dir;
    }

    function renderReportHistory(items) {
      if (!items.length) {
        byId("reportHistoryTable").textContent = "No completed reports found";
        return;
      }
      byId("reportHistoryTable").innerHTML = `
        <table>
          <thead><tr><th>Updated</th><th>Rank</th><th>Top5</th><th>Mention</th><th>Answers</th><th>Report</th></tr></thead>
          <tbody>${items.map((item) => `
            <tr>
              <td>${escapeHtml(item.updated_at || "")}</td>
              <td>${item.target_rank_by_top5 || "-"}</td>
              <td>${percent(item.target_top5_share)}</td>
              <td>${percent(item.target_model_mention_rate)}</td>
              <td>${item.answer_count || "-"}</td>
              <td><button class="button secondary inline" data-report-dir="${escapeHtml(item.report_dir)}" data-run-root="${escapeHtml(item.run_root)}">Open</button></td>
            </tr>`).join("")}</tbody>
        </table>`;
      byId("reportHistoryTable").querySelectorAll("button[data-report-dir]").forEach((button) => {
        button.addEventListener("click", () => loadReportPreview(button.dataset.reportDir, button.dataset.runRoot));
      });
    }

    async function refreshReportHistory() {
      const response = await fetch("/api/report-history?limit=20");
      const data = await response.json();
      if (data.error) {
        byId("reportHistoryTable").textContent = data.error;
        return;
      }
      renderReportHistory(data.items || []);
    }

    async function loadReportPreview(reportDir, runRoot) {
      const response = await fetch(`/api/report-preview?report_dir=${encodeURIComponent(reportDir)}`);
      const data = await response.json();
      if (data.error) {
        byId("reportPreview").textContent = data.error;
        return;
      }
      byId("reportPreview").textContent = data.content + (data.truncated ? "\n\n[truncated]" : "");
      if (runRoot) setMonitorRunRoot(runRoot);
      await loadPageDrilldown(reportDir);
    }

    function renderPageRows(rows, kind) {
      if (!rows || !rows.length) return `<div class="muted">No ${kind} pages found</div>`;
      if (kind === "top") {
        return `
          <div class="table-scroll">
          <table class="owned-pages-table">
            <colgroup>
              <col style="width:42%;">
              <col style="width:12%;">
              <col style="width:10%;">
              <col style="width:12%;">
              <col style="width:10%;">
            </colgroup>
            <thead><tr><th>URL</th><th class="metric-cell">Top5 queries</th><th class="metric-cell">Hits</th><th class="metric-cell">Best rank</th><th class="metric-cell">Models</th></tr></thead>
            <tbody>${rows.map((row) => `
              <tr>
                <td class="url-cell">${escapeHtml(row.url)}</td>
                <td class="metric-cell">${escapeHtml(row.top5_query_count)}</td>
                <td class="metric-cell">${escapeHtml(row.top5_hit_count)}</td>
                <td class="metric-cell">${escapeHtml(row.best_rank || "-")}</td>
                <td class="metric-cell">${escapeHtml(row.model_count)}</td>
              </tr>`).join("")}</tbody>
          </table>
          </div>`;
      }
      return `
        <div class="table-scroll">
        <table class="owned-pages-table">
          <colgroup>
            <col style="width:38%;">
            <col style="width:12%;">
            <col style="width:10%;">
            <col style="width:40%;">
          </colgroup>
          <thead><tr><th>URL</th><th class="metric-cell">Top5 queries</th><th class="metric-cell">Models</th><th>Suggested fix</th></tr></thead>
          <tbody>${rows.map((row) => `
            <tr>
              <td class="url-cell">${escapeHtml(row.url)}</td>
              <td class="metric-cell">${escapeHtml(row.top5_query_count)}</td>
              <td class="metric-cell">${escapeHtml(row.model_count)}</td>
              <td class="hint-cell">${escapeHtml(row.optimization_hint)}</td>
            </tr>`).join("")}</tbody>
        </table>
        </div>`;
    }

    async function loadPageDrilldown(reportDir) {
      const response = await fetch(`/api/page-drilldown?report_dir=${encodeURIComponent(reportDir)}`);
      const data = await response.json();
      if (data.error) {
        byId("ownedPageSource").textContent = data.error;
        byId("ownedTopPagesTable").textContent = "";
        byId("ownedWeakPagesTable").textContent = "";
        return;
      }
      byId("ownedPageSource").textContent = `Source: ${data.source} - ${data.report_dir}`;
      byId("ownedTopPagesTable").innerHTML = renderPageRows(data.top_pages || [], "top");
      byId("ownedWeakPagesTable").innerHTML = renderPageRows(data.weak_pages || [], "weak");
    }

    function renderModels(models) {
      byId("modelList").innerHTML = models.map((model, index) => `
        <label class="check">
          <input type="checkbox" name="model" value="${model.model}" ${index < 4 ? "checked" : ""}>
          ${model.model}
        </label>
      `).join("");
    }

    function renderCompetitors(competitors, aboveTarget) {
      const above = new Set((aboveTarget || []).map((item) => item.brand));
      byId("competitors").innerHTML = competitors.map((item) => {
        const marker = above.has(item.brand) ? "above AlphaXXXX" : "tracked";
        return `<span class="pill">${item.brand} · ${marker}</span>`;
      }).join("");
    }

    function renderCloud(cloud) {
      const rows = [
        ["S3 bucket", cloud.bucket || "-"],
        ["RDS host", cloud.rds_endpoint || "-"],
        ["AWS region", cloud.aws_region || "-"],
        ["AWS key", cloud.has_aws_access_key ? "configured" : "missing"],
        ["Postgres password", cloud.has_postgres_password ? "configured" : "missing"],
      ];
      byId("cloudRows").innerHTML = rows.map(([key, value]) => `<tr><th>${key}</th><td>${value}</td></tr>`).join("");
    }

    function checked(id) {
      return byId(id).checked ? "1" : "0";
    }

    function renderPipelineProgress(progress) {
      if (!progress) return '<span class="muted">-</span>';
      const percentValue = Number(progress.percent || 0);
      const bounded = Math.max(0, Math.min(100, percentValue));
      const label = progress.label || `${bounded.toFixed(1)}%`;
      return `
        <div class="progress-cell">
          <div class="progress-label">${label} (${bounded.toFixed(1)}%)</div>
          <div class="progress-track" aria-label="${label}" title="${label}">
            <div class="progress-fill" style="width:${bounded}%"></div>
          </div>
        </div>`;
    }

    function renderApiProgress(summary) {
      const totals = summary.totals || {};
      const expected = Number(totals.expected_api_calls || 0);
      const terminal = Number(totals.terminal_calls || 0);
      const bounded = expected ? Math.max(0, Math.min(100, (terminal / expected) * 100)) : 0;
      const label = expected ? `${terminal}/${expected} calls` : "0/0 calls";
      return `
        <div class="progress-cell">
          <div class="progress-label">${label} (${bounded.toFixed(1)}%)</div>
          <div class="progress-track" aria-label="${label}" title="${label}">
            <div class="progress-fill" style="width:${bounded}%"></div>
          </div>
        </div>`;
    }

    async function buildPlan() {
      const selectedStageLabel = byId("stageCommand").value;
      const params = collectRunParams();
      const response = await fetch(`/api/run-plan?${params.toString()}`);
      const plan = await response.json();
      lastPlan = plan;
      byId("commands").textContent = plan.commands.map((item, index) => `${index + 1}. ${item.label}\n${item.command}\n${item.note}`).join("\n\n");
      byId("warnings").innerHTML = plan.warnings.map((warning) => `<div class="warning">${warning}</div>`).join("");
      const stageCommands = plan.commands.filter((item) => item.command.startsWith("python scripts\\run_pipeline_step.py"));
      const stageSelect = byId("stageCommand");
      stageSelect.innerHTML = stageCommands.map((item) => `<option value="${item.label}">${item.label}</option>`).join("");
      if (Array.from(stageSelect.options).some((option) => option.value === selectedStageLabel)) {
        stageSelect.value = selectedStageLabel;
      }
    }

    function collectRunParams() {
      const params = new URLSearchParams();
      params.set("own_site_url", byId("ownSiteUrl").value);
      params.set("extra_site_urls", byId("extraSiteUrls").value);
      params.set("run_mode", byId("runMode").value);
      params.set("seed_queries_run_dir", byId("seedQueriesRunDir").value);
      params.set("pipeline_run_root", byId("pipelineRunRoot").value);
      params.set("recrawl_own_site", checked("recrawlOwnSite"));
      params.set("rescan_corpus", checked("rescanCorpus"));
      params.set("regenerate_scenarios", checked("regenerateScenarios"));
      params.set("sync_aws", checked("syncAws"));
      params.set("parallel_api", checked("parallelApi"));
      params.set("custom_queries_per_model", byId("customQueries").value);
      document.querySelectorAll('input[name="model"]:checked').forEach((item) => params.append("model", item.value));
      return params;
    }

    async function launchApiRun() {
      await buildPlan();
      const ok = window.confirm("Launch the API benchmark command shown in the plan? This may call external model APIs.");
      if (!ok) return;
      const params = collectRunParams();
      params.set("confirmed", "1");
      const response = await fetch("/api/launch-run", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: params.toString(),
      });
      const launch = await response.json();
      byId("launchStatus").textContent = `${launch.status}: pid ${launch.pid || "-"} - monitor ${launch.monitor_run_root || ""}`;
      if (launch.monitor_run_root) {
        setMonitorRunRoot(launch.monitor_run_root);
        await refreshMonitor();
      }
    }

    async function launchStage() {
      await buildPlan();
      const label = byId("stageCommand").value;
      if (!label) {
        byId("launchStatus").textContent = "No guarded pipeline step is available in the current plan.";
        return;
      }
      const ok = window.confirm(`Launch pipeline step: ${label}?`);
      if (!ok) return;
      const params = collectRunParams();
      params.set("confirmed", "1");
      params.set("command_label", label);
      const response = await fetch("/api/launch-stage", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: params.toString(),
      });
      const launch = await response.json();
      byId("launchStatus").textContent = `${launch.status}: ${launch.command_label || label} - pid ${launch.pid || "-"} - monitor ${launch.monitor_run_root || ""}`;
      if (launch.monitor_run_root) {
        setMonitorRunRoot(launch.monitor_run_root);
        await refreshMonitor();
      }
    }

    async function refreshMonitor() {
      const runRoot = byId("monitorRunRoot").value.trim();
      if (!runRoot) return;
      const response = await fetch(`/api/run-monitor?run_root=${encodeURIComponent(runRoot)}`);
      const monitor = await response.json();
      if (monitor.error) {
        byId("monitorLog").textContent = monitor.error;
        return;
      }
      byId("monitorStage").value = monitor.current_stage;
      byId("monitorApiCalls").textContent = monitor.totals.api_calls;
      byId("monitorFailures").textContent = monitor.totals.failures;
      const totalExpected = Number(monitor.totals.expected_api_calls || 0);
      const totalTerminal = Number(monitor.totals.terminal_calls || 0);
      const totalPct = (Number(monitor.totals.progress || 0) * 100).toFixed(1);
      byId("monitorProgress").textContent = `${totalTerminal}/${totalExpected} (${totalPct}%)`;
      byId("monitorModels").textContent = monitor.models.length;
      const health = monitor.health || {status: "unknown", issues: [], recommended_actions: []};
      byId("monitorHealth").textContent = health.status;
      renderLatestReport(monitor.report);
      if (monitor.report && monitor.report.report_dir) {
        await refreshReportHistory();
        await loadPageDrilldown(monitor.report.report_dir);
      }
      byId("monitorModelsTable").innerHTML = `
        <table>
          <thead><tr><th>Model</th><th>Status</th><th>Progress</th><th>API</th><th>Cache</th><th>Failures</th><th>Answers</th></tr></thead>
          <tbody>${monitor.models.map((item) => `
            <tr>
              <td>${escapeHtml(item.safe_name)}</td>
              <td>${escapeHtml(item.summary.status)}</td>
              <td>${renderApiProgress(item.summary)}</td>
              <td>${escapeHtml(item.summary.totals.api_calls)}</td>
              <td>${escapeHtml(item.summary.totals.cache_hits)}</td>
              <td>${escapeHtml(item.summary.totals.failures)}</td>
              <td>${escapeHtml(item.summary.outputs.answer_rows)}</td>
            </tr>`).join("")}</tbody>
        </table>`;
      const stageRows = Object.entries(monitor.pipeline.stages || {});
      byId("monitorStagesTable").innerHTML = `
        <table>
          <thead><tr><th>Stage</th><th>Status</th><th>Progress</th><th>Updated</th><th>Message</th></tr></thead>
          <tbody>${stageRows.map(([stage, item]) => `
            <tr>
              <td>${escapeHtml(stage)}</td>
              <td>${escapeHtml(item.status)}</td>
              <td>${renderPipelineProgress((monitor.pipeline_progress || {})[stage])}</td>
              <td>${escapeHtml(item.updated_at || "")}</td>
              <td>${escapeHtml(item.message || "")}</td>
            </tr>`).join("")}</tbody>
        </table>`;
      const pipelineLogs = (monitor.pipeline_log_tails || []).map((item) => {
        const lines = item.lines.length ? item.lines.join("\n") : "(no pipeline log yet)";
        return `# ${item.stage}\n${lines}`;
      });
      const healthLines = [`# chain health`, `status: ${health.status}`].concat((health.issues || []).map((issue) => `- ${issue}`));
      const recommendedActions = (health.recommended_actions || []).map((action) => `- ${action}`);
      if (recommendedActions.length) {
        healthLines.push("", "# recommended actions", ...recommendedActions);
      }
      const modelLogs = monitor.models.map((item) => {
        const lines = item.log_tail.length ? item.log_tail.join("\n") : "(no worker.log yet)";
        return `# ${item.safe_name}\n${lines}`;
      });
      byId("monitorLog").textContent = [healthLines.join("\n")].concat(pipelineLogs).concat(modelLogs).join("\n\n") || "(no logs yet)";
    }

    async function stopApiRun() {
      const runRoot = byId("monitorRunRoot").value.trim();
      if (!runRoot) return;
      const reason = window.prompt("Why stop this API run? Use 429, 402, or stalled as a short reason.", "stalled or API issue") || "";
      const ok = window.confirm(`Stop API run and its child workers?\n${runRoot}`);
      if (!ok) return;
      const params = new URLSearchParams();
      params.set("run_root", runRoot);
      params.set("reason", reason);
      params.set("confirmed", "1");
      const response = await fetch("/api/stop-run", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: params.toString(),
      });
      const result = await response.json();
      byId("launchStatus").textContent = `${result.status}: stop ${result.monitor_run_root || runRoot} pid ${result.pid || "-"}`;
      await refreshMonitor();
    }

    async function resumeApiRun() {
      const runRoot = byId("monitorRunRoot").value.trim();
      if (!runRoot) return;
      const ok = window.confirm(`Resume API run using existing output rows?\n${runRoot}`);
      if (!ok) return;
      const params = new URLSearchParams();
      params.set("run_root", runRoot);
      params.set("confirmed", "1");
      const response = await fetch("/api/resume-run", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: params.toString(),
      });
      const result = await response.json();
      byId("launchStatus").textContent = `${result.status}: resume ${result.monitor_run_root || runRoot} pid ${result.pid || "-"}`;
      if (result.monitor_run_root) setMonitorRunRoot(result.monitor_run_root);
      await refreshMonitor();
    }

    byId("refresh").addEventListener("click", loadState);
    byId("plan").addEventListener("click", buildPlan);
    byId("launchApi").addEventListener("click", launchApiRun);
    byId("launchStage").addEventListener("click", launchStage);
    byId("monitorRefresh").addEventListener("click", refreshMonitor);
    byId("stopApiRun").addEventListener("click", stopApiRun);
    byId("resumeApiRun").addEventListener("click", resumeApiRun);
    byId("linkedMonitorRoot").addEventListener("change", () => {
      setMonitorRunRoot(byId("linkedMonitorRoot").value);
      refreshMonitor();
    });
    byId("monitorRunRoot").addEventListener("change", () => {
      setMonitorRunRoot(byId("monitorRunRoot").value);
    });
    document.addEventListener("change", (event) => {
      if (event.target.closest("main")) buildPlan();
    });
    setInterval(() => {
      if (byId("monitorAutoRefresh").checked) refreshMonitor();
    }, 3000);
    loadState().then(refreshMonitor);
  </script>
</body>
</html>
"""

HTML = HTML.replace(" 路 ", " - ")


class UIHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html()
            return
        if parsed.path == "/api/state":
            self._send_json(build_dashboard_state(PROJECT_ROOT))
            return
        if parsed.path == "/api/report-history":
            params = parse_qs(parsed.query)
            limit_text = params.get("limit", ["20"])[0]
            try:
                limit = max(1, min(100, int(limit_text)))
            except ValueError:
                limit = 20
            items = list_report_history(PROJECT_ROOT, target_brand="AlphaXXXX", limit=limit)
            self._send_json({"items": [item.to_dict() for item in items]})
            return
        if parsed.path == "/api/report-preview":
            params = parse_qs(parsed.query)
            report_dir = params.get("report_dir", [""])[0]
            try:
                self._send_json(read_report_preview(PROJECT_ROOT, report_dir=report_dir))
            except (OSError, ValueError) as exc:
                self._send_json({"error": str(exc)})
            return
        if parsed.path == "/api/page-drilldown":
            params = parse_qs(parsed.query)
            report_dir = params.get("report_dir", [""])[0]
            try:
                self._send_json(
                    summarize_report_page_drilldown(PROJECT_ROOT, report_dir=report_dir, target_brand="AlphaXXXX")
                )
            except (OSError, ValueError) as exc:
                self._send_json({"error": str(exc)})
            return
        if parsed.path == "/api/run-plan":
            params = parse_qs(parsed.query)
            selected_models = params.get("model", [])
            extra_urls = [
                url.strip()
                for value in params.get("extra_site_urls", [])
                for url in value.replace(",", "\n").splitlines()
                if url.strip()
            ]
            custom_queries = params.get("custom_queries_per_model", [""])[0].strip()
            request = RunPlanRequest(
                platform=params.get("platform", ["auto"])[0],
                own_site_url=params.get("own_site_url", ["https://alphaxxxx.com/"])[0],
                extra_site_urls=extra_urls,
                run_mode=params.get("run_mode", ["quick"])[0],
                selected_models=selected_models,
                recrawl_own_site=params.get("recrawl_own_site", ["0"])[0] == "1",
                rescan_corpus=params.get("rescan_corpus", ["0"])[0] == "1",
                regenerate_scenarios=params.get("regenerate_scenarios", ["0"])[0] == "1",
                sync_aws=params.get("sync_aws", ["0"])[0] == "1",
                parallel_api=params.get("parallel_api", ["1"])[0] == "1",
                seed_queries_run_dir=params.get("seed_queries_run_dir", [""])[0],
                custom_queries_per_model=int(custom_queries) if custom_queries else None,
                pipeline_run_root=params.get("pipeline_run_root", ["<run-root>"])[0],
            )
            self._send_json(build_run_plan(request).to_dict())
            return
        if parsed.path == "/api/run-monitor":
            params = parse_qs(parsed.query)
            run_root = params.get("run_root", [""])[0]
            if not run_root:
                self._send_json({"error": "run_root is required"})
                return
            self._send_json(summarize_parallel_run(Path(run_root), target_brand="AlphaXXXX"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _run_request_from_params(self, params: dict[str, list[str]]) -> RunPlanRequest:
        selected_models = params.get("model", [])
        extra_urls = [
            url.strip()
            for value in params.get("extra_site_urls", [])
            for url in value.replace(",", "\n").splitlines()
            if url.strip()
        ]
        custom_queries = params.get("custom_queries_per_model", [""])[0].strip()
        return RunPlanRequest(
            platform=params.get("platform", ["auto"])[0],
            own_site_url=params.get("own_site_url", ["https://alphaxxxx.com/"])[0],
            extra_site_urls=extra_urls,
            run_mode=params.get("run_mode", ["quick"])[0],
            selected_models=selected_models,
            recrawl_own_site=params.get("recrawl_own_site", ["0"])[0] == "1",
            rescan_corpus=params.get("rescan_corpus", ["0"])[0] == "1",
            regenerate_scenarios=params.get("regenerate_scenarios", ["0"])[0] == "1",
            sync_aws=params.get("sync_aws", ["0"])[0] == "1",
            parallel_api=params.get("parallel_api", ["1"])[0] == "1",
            seed_queries_run_dir=params.get("seed_queries_run_dir", [""])[0],
            custom_queries_per_model=int(custom_queries) if custom_queries else None,
            pipeline_run_root=params.get("pipeline_run_root", ["<run-root>"])[0],
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        if parsed.path == "/api/launch-run":
            request = self._run_request_from_params(params)
            confirmed = params.get("confirmed", ["0"])[0] == "1"
            self._send_json(launch_guarded_run(project_root=PROJECT_ROOT, request=request, confirmed=confirmed))
            return
        if parsed.path == "/api/launch-stage":
            request = self._run_request_from_params(params)
            confirmed = params.get("confirmed", ["0"])[0] == "1"
            command_label = params.get("command_label", [""])[0]
            self._send_json(
                launch_guarded_stage(
                    project_root=PROJECT_ROOT,
                    request=request,
                    command_label=command_label,
                    confirmed=confirmed,
                )
            )
            return
        if parsed.path == "/api/stop-run":
            run_root = params.get("run_root", [""])[0]
            reason = params.get("reason", [""])[0]
            confirmed = params.get("confirmed", ["0"])[0] == "1"
            self._send_json(
                stop_guarded_run(
                    project_root=PROJECT_ROOT,
                    run_root=run_root,
                    reason=reason,
                    confirmed=confirmed,
                )
            )
            return
        if parsed.path == "/api/resume-run":
            run_root = params.get("run_root", [""])[0]
            confirmed = params.get("confirmed", ["0"])[0] == "1"
            self._send_json(
                resume_guarded_run(
                    project_root=PROJECT_ROOT,
                    run_root=run_root,
                    confirmed=confirmed,
                )
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local GEO benchmark console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), UIHandler)
    try:
        print(f"GEO Benchmark Console: http://{args.host}:{args.port}", flush=True)
    except OSError:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
