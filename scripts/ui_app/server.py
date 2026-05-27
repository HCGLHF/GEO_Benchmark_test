from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts.ui_app.dashboard import build_dashboard_state
from scripts.ui_app.deployment_action import handle_server_update_request
from scripts.ui_app.execution import launch_guarded_run, launch_guarded_stage, resume_guarded_run, stop_guarded_run
from scripts.ui_app.page_drilldown_summary import summarize_report_page_drilldown
from scripts.ui_app.report_history import list_report_history, read_report_download, read_report_preview
from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan
from scripts.ui_app.run_monitor import summarize_parallel_run


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _python_executable_for_platform(platform: str) -> str:
    requested = (platform or "auto").strip().lower()
    if requested == "auto":
        return sys.executable
    if sys.platform.startswith("win"):
        return sys.executable if requested == "windows" else ""
    return sys.executable if requested in {"linux", "wsl"} else ""


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GEO Benchmark Console</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #667085;
      --line: #d8dee9;
      --surface: #f4f6fa;
      --panel: #ffffff;
      --rail: #152033;
      --rail-muted: #9ca8ba;
      --accent: #0f766e;
      --accent-weak: #d9f4ef;
      --warn: #9a3412;
      --danger: #b42318;
      --ok: #067647;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--surface);
    }
    h1 { font-size: 20px; margin: 0; letter-spacing: 0; }
    h2 { font-size: 15px; margin: 0 0 12px; letter-spacing: 0; }
    .app-shell {
      display: grid;
      grid-template-columns: 76px minmax(0, 1fr);
      min-height: 100vh;
    }
    .nav-rail {
      position: sticky;
      top: 0;
      height: 100vh;
      background: var(--rail);
      color: #fff;
      display: grid;
      grid-template-rows: auto 1fr auto;
      justify-items: center;
      padding: 14px 10px;
      z-index: 2;
    }
    .rail-brand {
      width: 42px;
      height: 42px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: var(--accent);
      font-weight: 800;
    }
    .rail-nav {
      display: grid;
      gap: 8px;
      align-content: start;
      margin-top: 20px;
    }
    .rail-button {
      width: 44px;
      height: 44px;
      border: 0;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: var(--rail-muted);
      background: transparent;
      cursor: pointer;
    }
    .rail-button:hover,
    .rail-button.active {
      color: #fff;
      background: rgba(255, 255, 255, 0.12);
    }
    .rail-button[aria-current="page"] {
      color: #fff;
      background: var(--accent);
    }
    .rail-button:focus-visible,
    .button:focus-visible,
    input:focus-visible,
    textarea:focus-visible,
    select:focus-visible {
      outline: 2px solid #54c6b8;
      outline-offset: 2px;
    }
    .content-shell {
      min-width: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
    }
    .topbar {
      min-width: 0;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.88);
      backdrop-filter: blur(12px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 10px;
    }
    .workspace-wrap {
      padding: 18px;
      min-width: 0;
    }
    .workspace {
      display: none;
      min-width: 0;
    }
    .workspace.active {
      display: grid;
      gap: 16px;
    }
    .panel-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }
    .panel {
      grid-column: span 12;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
      overflow: hidden;
    }
    .panel.half { grid-column: span 6; }
    .panel.third { grid-column: span 4; }
    .panel.two-third { grid-column: span 8; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 82px;
      background: #fbfcfe;
      display: grid;
      gap: 8px;
    }
    .metric strong { display: block; font-size: 24px; line-height: 1.15; }
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
      border-radius: 7px;
      background: var(--accent);
      color: #fff;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 38px;
    }
    .button.secondary {
      background: #344054;
    }
    .button.ghost {
      color: var(--ink);
      background: #eef2f7;
    }
    .button.danger {
      background: var(--danger);
    }
    .button:disabled {
      opacity: 0.62;
      cursor: wait;
    }
    .button.inline {
      padding: 6px 9px;
      font-size: 12px;
    }
    .action-row {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .icon {
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      stroke: currentColor;
      fill: none;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      white-space: nowrap;
    }
    .status-badge.ok { color: var(--ok); background: #ecfdf3; border-color: #abefc6; }
    .status-badge.warning { color: var(--warn); background: #fff7ed; border-color: #fed7aa; }
    .status-badge.error { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
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
    .notice {
      border-radius: 7px;
      border: 1px solid var(--line);
      padding: 9px 10px;
      font-size: 13px;
      background: #fff;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .notice.warning { color: var(--warn); background: #fff7ed; border-color: #fed7aa; }
    .notice.error { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
    .notice.ok { color: var(--ok); background: #ecfdf3; border-color: #abefc6; }
    .log-toggle {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      padding: 8px 10px;
      margin-bottom: 8px;
      cursor: pointer;
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
    .trend-legend {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }
    .legend-dot.top5 { background: var(--accent); }
    .legend-dot.mention { background: #c2410c; }
    .trend-chart {
      min-height: 220px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      overflow: hidden;
    }
    .trend-chart svg {
      display: block;
      width: 100%;
      height: 220px;
    }
    .trend-axis,
    .trend-label {
      fill: var(--muted);
      font-size: 11px;
    }
    .trend-grid {
      stroke: #e6ebf2;
      stroke-width: 1;
    }
    .top-brands-list {
      display: grid;
      gap: 10px;
    }
    .top-brand-row {
      display: grid;
      grid-template-columns: 38px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 10px;
      min-width: 0;
    }
    .rank-badge {
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: var(--accent-weak);
      color: var(--accent);
      font-weight: 800;
      font-size: 13px;
    }
    .brand-name {
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .brand-metrics {
      color: var(--muted);
      font-size: 12px;
      text-align: right;
      white-space: nowrap;
    }
    .share-bar {
      height: 6px;
      border-radius: 999px;
      background: #e5e7eb;
      overflow: hidden;
      margin-top: 7px;
    }
    .share-fill {
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
    }
    @media (max-width: 1080px) {
      .panel.half, .panel.third, .panel.two-third { grid-column: span 12; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      .app-shell { grid-template-columns: 1fr; }
      .nav-rail {
        position: static;
        height: auto;
        grid-template-columns: auto 1fr;
        grid-template-rows: auto;
        justify-items: start;
      }
      .rail-nav {
        display: flex;
        overflow-x: auto;
        margin: 0 0 0 12px;
      }
      .top-brand-row {
        grid-template-columns: 34px minmax(0, 1fr);
      }
      .brand-metrics {
        grid-column: 2;
        text-align: left;
      }
      .metrics, .row, .checks { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="nav-rail" aria-label="Primary">
      <div class="rail-brand" title="AlphaXXXX">AX</div>
      <nav class="rail-nav" aria-label="Workspaces">
        <button class="rail-button active" data-view-target="overview" aria-label="Overview" aria-current="page" title="Overview" type="button"><svg class="icon icon-overview" viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg></button>
        <button class="rail-button" data-view-target="run-setup" aria-label="Run setup" title="Run setup" type="button"><svg class="icon icon-run" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button>
        <button class="rail-button" data-view-target="monitor" aria-label="Run monitor" title="Run monitor" type="button"><svg class="icon icon-monitor" viewBox="0 0 24 24"><path d="M4 19V5M4 19h16M8 15v-4M12 15V7M16 15v-6"/></svg></button>
        <button class="rail-button" data-view-target="reports" aria-label="Reports" title="Reports" type="button"><svg class="icon icon-reports" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7zM14 3v5h5M9 14h8M9 18h6"/></svg></button>
        <button class="rail-button" data-view-target="pages" aria-label="Owned pages" title="Owned pages" type="button"><svg class="icon icon-pages" viewBox="0 0 24 24"><path d="M4 5h16v14H4zM8 9h8M8 13h5M8 17h7"/></svg></button>
        <button class="rail-button" data-view-target="cloud" aria-label="Cloud store" title="Cloud store" type="button"><svg class="icon icon-cloud" viewBox="0 0 24 24"><path d="M17 18H7a4 4 0 1 1 .8-7.9A5.5 5.5 0 0 1 18.4 12 3 3 0 0 1 17 18z"/></svg></button>
        <button class="rail-button" data-view-target="commands" aria-label="Commands" title="Commands" type="button"><svg class="icon icon-commands" viewBox="0 0 24 24"><path d="M4 17l5-5-5-5M12 19h8"/></svg></button>
      </nav>
    </aside>
    <div class="content-shell">
      <header class="topbar">
        <div>
          <h1 id="activeWorkspaceTitle">Overview</h1>
          <div class="muted">GEO Benchmark Console</div>
        </div>
        <div class="topbar-actions">
          <span class="status-badge" id="globalHealthBadge">status unknown</span>
          <button class="button ghost" id="refresh" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M20 6v5h-5M4 18v-5h5M18.7 9A7 7 0 0 0 6.8 6.8M5.3 15A7 7 0 0 0 17.2 17.2"/></svg>Refresh</button>
        </div>
      </header>
      <main class="workspace-wrap">
        <section class="workspace active" data-view="overview">
          <div class="panel-grid">
            <div class="panel half">
              <h2>Resource Library</h2>
              <div class="metrics">
                <div class="metric"><strong id="companyCount">0</strong><span>companies</span></div>
                <div class="metric"><strong id="urlCount">0</strong><span>URLs</span></div>
                <div class="metric"><strong id="documentCount">0</strong><span>documents</span></div>
                <div class="metric"><strong id="chunkCount">0</strong><span>chunks</span></div>
              </div>
            </div>
            <div class="panel half">
              <h2>Latest Report</h2>
              <div class="metrics">
                <div class="metric"><strong id="targetRank">-</strong><span>AlphaXXXX rank</span></div>
                <div class="metric"><strong id="targetTop5">-</strong><span>Retrieval Top5</span></div>
                <div class="metric"><strong id="targetMention">-</strong><span>Model mention</span></div>
                <div class="metric"><strong id="answerCount">-</strong><span>answers</span></div>
              </div>
              <div id="reportPath" class="muted" style="margin-top:10px;"></div>
            </div>
            <div class="panel two-third">
              <h2>Competitors</h2>
              <div id="competitors"></div>
            </div>
            <div class="panel third">
              <h2>Next Action</h2>
              <button class="button" type="button" data-view-target="run-setup"><svg class="icon" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>Prepare Run</button>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="run-setup">
          <div class="panel-grid">
            <div class="panel two-third">
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
                <label>Platform
                  <select id="platform">
                    <option value="auto">auto</option>
                    <option value="windows">windows</option>
                    <option value="wsl">wsl</option>
                    <option value="linux">linux</option>
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
                <label class="check"><input id="syncAws" type="checkbox"> Sync corpus AWS</label>
                <label class="check"><input id="syncRunArtifacts" type="checkbox" checked> Sync run artifacts</label>
                <label class="check"><input id="parallelApi" type="checkbox" checked> Parallel API</label>
                <label class="check">Custom queries <input id="customQueries" type="number" min="1" value=""></label>
              </div>
            </div>
            <div class="panel third">
              <h2>Models</h2>
              <div class="list" id="modelList"></div>
            </div>
            <div class="panel">
              <h2>Actions</h2>
              <div>
                <button class="button" id="plan" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M7 8h10M7 12h10M7 16h6M5 3h14v18H5z"/></svg>Build Run Plan</button>
                <button class="button secondary" id="launchApi" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>Launch API Run</button>
              </div>
              <div class="row" style="margin-top:12px;">
                <label>Pipeline step
                  <select id="stageCommand"></select>
                </label>
                <label>Step launch
                  <button class="button secondary" id="launchStage" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>Launch Step</button>
                </label>
              </div>
              <div id="launchStatus" class="muted" style="margin-top:10px;"></div>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="monitor">
          <div class="panel-grid">
            <div class="panel">
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
                <button class="button secondary" id="monitorRefresh" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M20 6v5h-5M4 18v-5h5M18.7 9A7 7 0 0 0 6.8 6.8M5.3 15A7 7 0 0 0 17.2 17.2"/></svg>Refresh Monitor</button>
                <button class="button danger" id="stopApiRun" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>Stop API Run</button>
                <button class="button" id="resumeApiRun" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>Resume API Run</button>
                <label class="check" style="display:inline-flex; margin-left:8px; width:auto;">
                  <input id="monitorAutoRefresh" type="checkbox" checked> Auto-refresh
                </label>
              </div>
            </div>
            <div class="panel">
              <h2>Model Workers</h2>
              <div id="monitorModelsTable"></div>
            </div>
            <div class="panel">
              <h2>Pipeline Stages</h2>
              <div id="monitorStagesTable"></div>
            </div>
            <div class="panel">
              <h2>Monitor Log</h2>
              <button class="log-toggle" type="button" data-log-target="monitorLog">Monitor logs</button>
              <pre id="monitorLog"></pre>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="reports">
          <div class="panel-grid">
            <div class="panel half">
              <h2>Performance Trend</h2>
              <div class="trend-legend" aria-label="Report trend legend">
                <span class="legend-item"><span class="legend-dot top5"></span>Top5</span>
                <span class="legend-item"><span class="legend-dot mention"></span>Mention</span>
              </div>
              <div id="reportTrendChart" class="trend-chart muted">No report trend loaded</div>
            </div>
            <div class="panel half">
              <h2>Latest Top 5 Overview</h2>
              <div id="latestTopBrands" class="top-brands-list muted">No latest report loaded</div>
            </div>
            <div class="panel half">
              <h2>Report History</h2>
              <div id="reportHistoryTable" class="muted">No report history loaded</div>
            </div>
            <div class="panel half">
              <h2>Report Preview</h2>
              <pre id="reportPreview">(select a report)</pre>
            </div>
            <div class="panel">
              <h2>URL / Domain Top5 Winners</h2>
              <div id="reportUrlDomainDrilldown" class="muted">No report loaded</div>
            </div>
            <div class="panel half">
              <h2>Persona / Stage Losses</h2>
              <div id="reportPersonaStageDrilldown" class="muted">No report loaded</div>
            </div>
            <div class="panel half">
              <h2>Money Page Actions</h2>
              <div id="reportMoneyPageActions" class="muted">No report loaded</div>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="pages">
          <div class="panel-grid">
            <div class="panel">
              <h2>Owned Page Drilldown</h2>
              <div id="ownedPageSource" class="muted">Select or load a report</div>
            </div>
            <div class="panel half">
              <h2>Top5 Retrieved Pages</h2>
              <div id="ownedTopPagesTable" class="muted">No report loaded</div>
            </div>
            <div class="panel half">
              <h2>Weak Pages To Optimize</h2>
              <div id="ownedWeakPagesTable" class="muted">No report loaded</div>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="cloud">
          <div class="panel-grid">
            <div class="panel half">
              <h2>Cloud Store</h2>
              <table>
                <tbody id="cloudRows"></tbody>
              </table>
            </div>
            <div class="panel half">
              <h2>Deployment Status</h2>
              <table>
                <tbody id="deploymentRows"></tbody>
              </table>
            </div>
            <div class="panel">
              <h2>Server Data Refresh</h2>
              <div class="muted">Runs the fixed server workflow: git pull, hydrate artifacts, verify cloud import, restart service, then check /api/state.</div>
              <div style="margin-top:12px;">
                <button class="button secondary" id="runServerUpdate" type="button"><svg class="icon" viewBox="0 0 24 24"><path d="M20 6v5h-5M4 18v-5h5M18.7 9A7 7 0 0 0 6.8 6.8M5.3 15A7 7 0 0 0 17.2 17.2"/></svg>Run Server Update</button>
              </div>
              <div id="serverUpdateStatus" class="muted" style="margin-top:10px;"></div>
            </div>
            <div class="panel">
              <h2>Deployment Log Details</h2>
              <div id="deploymentStepsTable" class="muted">No deployment log loaded</div>
            </div>
          </div>
        </section>
        <section class="workspace" data-view="commands">
          <div class="panel">
            <h2>Dry Run Commands</h2>
            <button class="log-toggle" type="button" data-log-target="commands">Command preview</button>
            <pre id="commands"></pre>
            <div id="warnings"></div>
          </div>
        </section>
      </main>
    </div>
  </div>
  <script>
    let state = null;
    let lastPlan = null;

    const workspaceTitles = {
      overview: "Overview",
      "run-setup": "Run Setup",
      monitor: "Run Monitor",
      reports: "Reports",
      pages: "Owned Pages",
      cloud: "Cloud Store",
      commands: "Commands",
    };

    const byId = (id) => document.getElementById(id);
    const monitorStorageKey = "geo.monitorRunRoot";
    const percent = (value) => value === null || value === undefined ? "-" : `${Number(value).toFixed(1)}%`;
    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

    function setCurrentView(view) {
      view = workspaceTitles[view] ? view : "overview";
      document.querySelectorAll("[data-view-target]").forEach((button) => {
        const active = button.dataset.viewTarget === view;
        button.classList.toggle("active", active);
        if (active) {
          button.setAttribute("aria-current", "page");
        } else {
          button.removeAttribute("aria-current");
        }
      });
      document.querySelectorAll(".workspace").forEach((workspace) => {
        workspace.classList.toggle("active", workspace.dataset.view === view);
      });
      byId("activeWorkspaceTitle").textContent = workspaceTitles[view];
      localStorage.setItem("geo.currentView", view);
    }

    function setGlobalHealth(status) {
      const value = String(status || "unknown");
      let tone = "";
      if (["ok", "complete", "completed"].includes(value)) tone = "ok";
      if (["warning", "complete_with_model_warnings", "interrupted"].includes(value)) tone = "warning";
      if (["error", "failed"].includes(value)) tone = "error";
      const globalHealthBadge = byId("globalHealthBadge");
      globalHealthBadge.className = `status-badge ${tone}`;
      globalHealthBadge.textContent = displayHealthStatus(value);
    }

    function displayHealthStatus(value) {
      const labels = {
        ok: "Ready",
        complete: "Complete",
        completed: "Complete",
        warning: "Warning",
        complete_with_model_warnings: "Warnings",
        interrupted: "Interrupted",
        error: "Error",
        failed: "Failed",
        unknown: "Status unknown",
      };
      return labels[value] || value.replaceAll("_", " ");
    }

    function setNotice(id, message, tone = "") {
      const node = byId(id);
      node.className = tone ? `notice ${tone}` : "muted";
      node.textContent = message || "";
    }

    function commandText(command) {
      return Array.isArray(command) ? command.join(" ") : String(command || "");
    }

    async function withButtonBusy(button, busyText, action) {
      button.dataset.originalText = button.innerHTML;
      button.disabled = true;
      button.textContent = busyText;
      try {
        return await action();
      } finally {
        button.disabled = false;
        button.innerHTML = button.dataset.originalText;
      }
    }

    function toggleLogPanel(targetId) {
      const target = byId(targetId);
      target.hidden = !target.hidden;
    }

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
      renderDeployment(state.deployment);
      renderReportHistory(state.report_history || []);
      renderReportTrendChart(state.report_history || []);
      renderLatestTopBrands(report.top_brands || []);
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
      renderLatestTopBrands(report.top_brands || []);
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
              <td>
                <span class="action-row">
                  <button class="button secondary inline" data-report-dir="${escapeHtml(item.report_dir)}" data-run-root="${escapeHtml(item.run_root)}">Open</button>
                  <button class="button ghost inline" data-report-download-dir="${escapeHtml(item.report_dir)}">Download</button>
                </span>
              </td>
            </tr>`).join("")}</tbody>
        </table>`;
      byId("reportHistoryTable").querySelectorAll("button[data-report-dir]").forEach((button) => {
        button.addEventListener("click", () => loadReportPreview(button.dataset.reportDir, button.dataset.runRoot));
      });
      byId("reportHistoryTable").querySelectorAll("button[data-report-download-dir]").forEach((button) => {
        button.addEventListener("click", () => downloadReport(button.dataset.reportDownloadDir));
      });
    }

    function downloadReport(reportDir) {
      window.location.href = `/api/report-download?report_dir=${encodeURIComponent(reportDir)}`;
    }

    function renderReportTrendChart(items) {
      const node = byId("reportTrendChart");
      const series = (items || [])
        .filter((item) => item && (
          item.target_top5_share !== null && item.target_top5_share !== undefined ||
          item.target_model_mention_rate !== null && item.target_model_mention_rate !== undefined
        ))
        .sort((a, b) => String(a.updated_at || "").localeCompare(String(b.updated_at || "")))
        .slice(-8);
      if (!series.length) {
        node.className = "trend-chart muted";
        node.textContent = "No report trend loaded";
        return;
      }

      const width = 640;
      const height = 220;
      const pad = {left: 42, right: 18, top: 18, bottom: 34};
      const plotWidth = width - pad.left - pad.right;
      const plotHeight = height - pad.top - pad.bottom;
      const xFor = (index) => pad.left + (series.length === 1 ? plotWidth / 2 : (plotWidth * index) / (series.length - 1));
      const yFor = (value) => pad.top + plotHeight - (Math.max(0, Math.min(100, Number(value || 0))) / 100) * plotHeight;
      const pathFor = (key) => series.map((item, index) => `${index === 0 ? "M" : "L"} ${xFor(index).toFixed(1)} ${yFor(item[key]).toFixed(1)}`).join(" ");
      const circlesFor = (key, className) => series.map((item, index) => (
        `<circle class="${className}" cx="${xFor(index).toFixed(1)}" cy="${yFor(item[key]).toFixed(1)}" r="3.8"><title>${escapeHtml(percent(item[key]))}</title></circle>`
      )).join("");
      const labels = series.map((item, index) => {
        const label = String(item.updated_at || item.run_root || `#${index + 1}`).slice(0, 10);
        return `<text class="trend-label" x="${xFor(index).toFixed(1)}" y="208" text-anchor="middle">${escapeHtml(label)}</text>`;
      }).join("");

      node.className = "trend-chart";
      node.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Top5 and mention trend line graph">
          <line class="trend-grid" x1="${pad.left}" y1="${yFor(100)}" x2="${width - pad.right}" y2="${yFor(100)}"></line>
          <line class="trend-grid" x1="${pad.left}" y1="${yFor(50)}" x2="${width - pad.right}" y2="${yFor(50)}"></line>
          <line class="trend-grid" x1="${pad.left}" y1="${yFor(0)}" x2="${width - pad.right}" y2="${yFor(0)}"></line>
          <text class="trend-axis" x="8" y="${yFor(100) + 4}">100%</text>
          <text class="trend-axis" x="14" y="${yFor(50) + 4}">50%</text>
          <text class="trend-axis" x="20" y="${yFor(0) + 4}">0%</text>
          <path d="${pathFor("target_top5_share")}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${pathFor("target_model_mention_rate")}" fill="none" stroke="#c2410c" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <g fill="var(--accent)">${circlesFor("target_top5_share", "trend-top5-point")}</g>
          <g fill="#c2410c">${circlesFor("target_model_mention_rate", "trend-mention-point")}</g>
          ${labels}
        </svg>`;
    }

    function renderLatestTopBrands(brands) {
      const node = byId("latestTopBrands");
      const rows = (brands || []).slice(0, 5);
      if (!rows.length) {
        node.className = "top-brands-list muted";
        node.textContent = "No latest report loaded";
        return;
      }
      node.className = "top-brands-list";
      node.innerHTML = rows.map((brand, index) => {
        const top5 = Math.max(0, Math.min(100, Number(brand.top5_share || 0)));
        return `
          <div class="top-brand-row">
            <div class="rank-badge">${index + 1}</div>
            <div>
              <div class="brand-name">${escapeHtml(brand.brand)}</div>
              <div class="share-bar" aria-label="${escapeHtml(brand.brand)} Top5 share">
                <div class="share-fill" style="width:${top5}%"></div>
              </div>
            </div>
            <div class="brand-metrics">
              <strong>${percent(brand.top5_share)}</strong> Top5<br>
              ${percent(brand.model_mention_rate)} Mention<br>
              ${escapeHtml(brand.top5_count || 0)}/${escapeHtml(brand.query_count || 0)} hits
            </div>
          </div>`;
      }).join("");
    }

    async function refreshReportHistory() {
      const response = await fetch("/api/report-history?limit=20");
      const data = await response.json();
      if (data.error) {
        byId("reportHistoryTable").textContent = data.error;
        return;
      }
      renderReportHistory(data.items || []);
      renderReportTrendChart(data.items || []);
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

    function renderReportDeepDrilldown(data) {
      const urls = data.url_rankings || [];
      const domains = data.domain_rankings || [];
      const personaStages = data.persona_stage_losses || [];
      const actions = data.content_actions || [];
      const intents = data.page_intent_groups || [];
      byId("reportUrlDomainDrilldown").innerHTML = renderUrlDomainRows(urls, domains);
      byId("reportPersonaStageDrilldown").innerHTML = renderPersonaStageRows(personaStages);
      byId("reportMoneyPageActions").innerHTML = renderActionRows(actions, intents);
    }

    function renderUrlDomainRows(urls, domains) {
      if (!urls.length && !domains.length) return `<div class="muted">No URL/domain diagnostics available for this report</div>`;
      const urlRows = urls.slice(0, 8).map((row) => `
        <tr>
          <td class="metric-cell">${escapeHtml(row.rank || "-")}</td>
          <td class="url-cell">${escapeHtml(row.url || "")}</td>
          <td>${escapeHtml(row.domain || "")}</td>
          <td>${escapeHtml(row.brand || "")}</td>
          <td class="metric-cell">${escapeHtml(row.top5_query_count || "0")}</td>
          <td>${escapeHtml(row.page_intent || "")}</td>
        </tr>`).join("");
      const domainRows = domains.slice(0, 6).map((row) => `
        <tr>
          <td class="metric-cell">${escapeHtml(row.rank || "-")}</td>
          <td>${escapeHtml(row.domain || "")}</td>
          <td>${escapeHtml(row.brand || "")}</td>
          <td class="metric-cell">${escapeHtml(row.top5_query_count || "0")}</td>
          <td class="url-cell">${escapeHtml(row.top_urls || "")}</td>
        </tr>`).join("");
      return `
        <div class="table-scroll">
          <table class="owned-pages-table">
            <thead><tr><th>#</th><th>URL</th><th>Domain</th><th>Brand</th><th class="metric-cell">Top5 queries</th><th>Intent</th></tr></thead>
            <tbody>${urlRows}</tbody>
          </table>
        </div>
        <div class="table-scroll" style="margin-top:10px;">
          <table class="owned-pages-table">
            <thead><tr><th>#</th><th>Domain</th><th>Brand</th><th class="metric-cell">Top5 queries</th><th>Top URLs</th></tr></thead>
            <tbody>${domainRows}</tbody>
          </table>
        </div>`;
    }

    function renderPersonaStageRows(rows) {
      if (!rows.length) return `<div class="muted">No persona/stage diagnostics available for this report</div>`;
      return `
        <div class="table-scroll">
        <table class="owned-pages-table">
          <thead><tr><th>Persona</th><th>Stage</th><th class="metric-cell">Queries</th><th class="metric-cell">Top5</th><th>Winner</th><th>Why losing</th></tr></thead>
          <tbody>${rows.slice(0, 10).map((row) => `
            <tr>
              <td>${escapeHtml(row.persona || "")}</td>
              <td>${escapeHtml(row.journey_stage || "")}</td>
              <td class="metric-cell">${escapeHtml(row.query_count || "0")}</td>
              <td class="metric-cell">${percent(row.target_top5_share)}</td>
              <td>${escapeHtml(row.leading_winner || "")}</td>
              <td class="hint-cell">${escapeHtml(row.primary_loss_reasons || row.recommended_action || "")}</td>
            </tr>`).join("")}</tbody>
        </table>
        </div>`;
    }

    function renderActionRows(actions, intents) {
      if (!actions.length && !intents.length) return `<div class="muted">No money-page action plan available for this report</div>`;
      const actionRows = actions.slice(0, 10).map((row) => `
        <tr>
          <td class="metric-cell">${escapeHtml(row.priority || "")}</td>
          <td class="url-cell">${escapeHtml(row.url || "")}</td>
          <td>${escapeHtml(row.page_intent || "")}</td>
          <td class="url-cell">${escapeHtml(row.competitor_benchmark_url || "")}</td>
          <td class="hint-cell">${escapeHtml(row.content_gaps || "")}</td>
          <td class="hint-cell">${escapeHtml(row.schema_recommendation || "")}</td>
        </tr>`).join("");
      const intentRows = intents.slice(0, 6).map((row) => `
        <tr>
          <td>${escapeHtml(row.page_intent || "")}</td>
          <td class="metric-cell">${escapeHtml(row.weak_page_count || "0")}</td>
          <td class="metric-cell">${escapeHtml(row.zero_top5_count || "0")}</td>
          <td class="hint-cell">${escapeHtml(row.recommended_focus || "")}</td>
        </tr>`).join("");
      return `
        <div class="table-scroll">
        <table class="owned-pages-table">
          <thead><tr><th>Priority</th><th>URL</th><th>Intent</th><th>Benchmark</th><th>Content gaps</th><th>Schema</th></tr></thead>
          <tbody>${actionRows}</tbody>
        </table>
        </div>
        <div class="table-scroll" style="margin-top:10px;">
        <table class="owned-pages-table">
          <thead><tr><th>Intent</th><th class="metric-cell">Weak</th><th class="metric-cell">Zero Top5</th><th>Focus</th></tr></thead>
          <tbody>${intentRows}</tbody>
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
        byId("reportUrlDomainDrilldown").textContent = data.error;
        byId("reportPersonaStageDrilldown").textContent = "";
        byId("reportMoneyPageActions").textContent = "";
        return;
      }
      byId("ownedPageSource").textContent = `Source: ${data.source} - ${data.report_dir}`;
      byId("ownedTopPagesTable").innerHTML = renderPageRows(data.top_pages || [], "top");
      byId("ownedWeakPagesTable").innerHTML = renderPageRows(data.weak_pages || [], "weak");
      renderReportDeepDrilldown(data);
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
      byId("cloudRows").innerHTML = rows.map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(value)}</td></tr>`).join("");
    }

    function renderDeployment(deployment) {
      deployment = deployment || {};
      const git = deployment.git || {};
      const last = deployment.last_deployment || {};
      const verification = deployment.cloud_verification || {};
      const apiState = deployment.api_state || {};
      const updateAction = deployment.update_action || {};
      const verifierStatus = verification.ok === null || verification.ok === undefined ? "-" : (verification.ok ? "ok" : "failed");
      const rows = [
        ["Git branch", git.branch || "-"],
        ["Git commit", git.commit || "-"],
        ["Default corpus", deployment.default_corpus_version || "-"],
        ["Last deploy", `${last.status || "missing"}${last.completed_at ? " / " + last.completed_at : ""}`],
        ["Failed step", last.failed_step || "-"],
        ["Cloud verifier", verifierStatus],
        ["Cloud artifacts", verification.artifacts ?? "-"],
        ["API documents", apiState.document_count ?? "-"],
        ["API chunks", apiState.chunk_count ?? "-"],
        ["Latest report", apiState.latest_report_dir || "-"],
      ];
      byId("deploymentRows").innerHTML = rows.map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(value)}</td></tr>`).join("");
      byId("runServerUpdate").disabled = Boolean(updateAction.busy);
      if (updateAction.busy) {
        setNotice("serverUpdateStatus", `Deployment running: pid ${updateAction.pid || "-"} started ${updateAction.started_at || "-"}`, "warning");
      } else if (updateAction.stale) {
        setNotice("serverUpdateStatus", `Previous update launcher is stale; latest completed deployment log is shown below.`, "warning");
      } else {
        setNotice("serverUpdateStatus", "");
      }
      renderDeploymentSteps(deployment.deployment_steps || []);
    }

    function renderDeploymentSteps(steps) {
      if (!steps.length) {
        byId("deploymentStepsTable").textContent = "No deployment log loaded";
        return;
      }
      byId("deploymentStepsTable").innerHTML = `
        <table>
          <thead><tr><th>Step</th><th>Status</th><th>Attempts</th><th>Return</th><th>Duration</th></tr></thead>
          <tbody>${steps.map((step) => `
            <tr>
              <td>${escapeHtml(step.name || "-")}</td>
              <td>${escapeHtml(step.status || "-")}</td>
              <td>${escapeHtml(step.attempts ?? "-")}</td>
              <td>${escapeHtml(step.returncode ?? "-")}</td>
              <td>${escapeHtml(step.duration_seconds ?? "-")}</td>
            </tr>`).join("")}</tbody>
        </table>`;
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

    function isPipelineStepCommand(command) {
      const normalized = String(command || "").replaceAll("\\", "/");
      return normalized.startsWith("python scripts/run_pipeline_step.py")
        || normalized.startsWith("python3 scripts/run_pipeline_step.py")
        || normalized.includes("/python scripts/run_pipeline_step.py")
        || normalized.includes("/python3 scripts/run_pipeline_step.py")
        || normalized.includes("/python.exe scripts/run_pipeline_step.py");
    }

    async function buildPlan() {
      const selectedStageLabel = byId("stageCommand").value;
      const params = collectRunParams();
      const response = await fetch(`/api/run-plan?${params.toString()}`);
      const plan = await response.json();
      lastPlan = plan;
      byId("commands").textContent = plan.commands.map((item, index) => `${index + 1}. ${item.label}\n${item.command}\n${item.note}`).join("\n\n");
      byId("warnings").innerHTML = plan.warnings.map((warning) => `<div class="warning">${warning}</div>`).join("");
      const stageCommands = plan.commands.filter((item) => isPipelineStepCommand(item.command));
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
      params.set("platform", byId("platform").value);
      params.set("seed_queries_run_dir", byId("seedQueriesRunDir").value);
      params.set("pipeline_run_root", byId("pipelineRunRoot").value);
      params.set("recrawl_own_site", checked("recrawlOwnSite"));
      params.set("rescan_corpus", checked("rescanCorpus"));
      params.set("regenerate_scenarios", checked("regenerateScenarios"));
      params.set("sync_aws", checked("syncAws"));
      params.set("sync_run_artifacts", checked("syncRunArtifacts"));
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
      setNotice("launchStatus", `${launch.status}: pid ${launch.pid || "-"} - monitor ${launch.monitor_run_root || ""}`, "ok");
      if (launch.monitor_run_root) {
        setMonitorRunRoot(launch.monitor_run_root);
        await refreshMonitor();
      }
    }

    async function launchStage() {
      await buildPlan();
      const label = byId("stageCommand").value;
      if (!label) {
        setNotice("launchStatus", "No guarded pipeline step is available in the current plan.", "warning");
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
      setNotice("launchStatus", `${launch.status}: ${launch.command_label || label} - pid ${launch.pid || "-"} - monitor ${launch.monitor_run_root || ""}`, "ok");
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
      setGlobalHealth(health.status);
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
      setNotice("launchStatus", `${result.status}: stop ${result.monitor_run_root || runRoot} pid ${result.pid || "-"}`, "warning");
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
      setNotice("launchStatus", `${result.status}: resume ${result.monitor_run_root || runRoot} pid ${result.pid || "-"}`, "ok");
      if (result.monitor_run_root) setMonitorRunRoot(result.monitor_run_root);
      await refreshMonitor();
    }

    async function runServerUpdate() {
      const ok = window.confirm("Run server update? This will git pull, hydrate artifacts, verify cloud import, restart service, and check /api/state.");
      if (!ok) return;
      const button = byId("runServerUpdate");
      const originalText = button.innerHTML;
      button.disabled = true;
      button.textContent = "Starting...";
      const params = new URLSearchParams();
      params.set("confirmed", "1");
      try {
        const response = await fetch("/api/server-update", {
          method: "POST",
          headers: {"Content-Type": "application/x-www-form-urlencoded"},
          body: params.toString(),
        });
        const result = await response.json();
        const tone = result.status === "launched" ? "ok" : "warning";
        let message = `${result.status}: ${result.pid ? "pid " + result.pid : result.confirmation_message || ""}`;
        if (result.status === "manual_required") {
          message = `${result.status}: ${result.message || ""}\n${result.launcher_reason || ""}\nManual command: ${commandText(result.manual_command)}`;
        }
        if (result.status === "busy") {
          message = `${result.status}: deployment already running since ${result.started_at || "-"} pid ${result.pid || "-"}`;
        }
        setNotice("serverUpdateStatus", message, tone);
        if (result.status !== "manual_required") {
          await loadState();
        }
      } finally {
        button.innerHTML = originalText;
        const busy = state && state.deployment && state.deployment.update_action && state.deployment.update_action.busy;
        button.disabled = Boolean(busy);
      }
    }

    byId("refresh").addEventListener("click", loadState);
    byId("plan").addEventListener("click", buildPlan);
    byId("launchApi").addEventListener("click", () => withButtonBusy(byId("launchApi"), "Launching...", launchApiRun));
    byId("launchStage").addEventListener("click", () => withButtonBusy(byId("launchStage"), "Launching...", launchStage));
    byId("monitorRefresh").addEventListener("click", () => withButtonBusy(byId("monitorRefresh"), "Refreshing...", refreshMonitor));
    byId("stopApiRun").addEventListener("click", () => withButtonBusy(byId("stopApiRun"), "Stopping...", stopApiRun));
    byId("resumeApiRun").addEventListener("click", () => withButtonBusy(byId("resumeApiRun"), "Resuming...", resumeApiRun));
    byId("runServerUpdate").addEventListener("click", runServerUpdate);
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
    document.querySelectorAll("[data-view-target]").forEach((button) => {
      button.addEventListener("click", () => setCurrentView(button.dataset.viewTarget));
    });
    document.querySelectorAll("[data-log-target]").forEach((button) => {
      button.addEventListener("click", () => toggleLogPanel(button.dataset.logTarget));
    });
    setInterval(() => {
      if (byId("monitorAutoRefresh").checked) refreshMonitor();
    }, 3000);
    setCurrentView(localStorage.getItem("geo.currentView") || "overview");
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

    def _send_download(self, payload: dict) -> None:
        body = str(payload["content"]).encode("utf-8")
        filename = str(payload["filename"]).replace('"', "")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", str(payload["content_type"]))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
        if parsed.path == "/api/report-download":
            params = parse_qs(parsed.query)
            report_dir = params.get("report_dir", [""])[0]
            try:
                self._send_download(read_report_download(PROJECT_ROOT, report_dir=report_dir))
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
                python_executable=_python_executable_for_platform(params.get("platform", ["auto"])[0]),
                own_site_url=params.get("own_site_url", ["https://alphaxxxx.com/"])[0],
                extra_site_urls=extra_urls,
                run_mode=params.get("run_mode", ["quick"])[0],
                selected_models=selected_models,
                recrawl_own_site=params.get("recrawl_own_site", ["0"])[0] == "1",
                rescan_corpus=params.get("rescan_corpus", ["0"])[0] == "1",
                regenerate_scenarios=params.get("regenerate_scenarios", ["0"])[0] == "1",
                sync_aws=params.get("sync_aws", ["0"])[0] == "1",
                sync_run_artifacts=params.get("sync_run_artifacts", ["1"])[0] == "1",
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
            python_executable=_python_executable_for_platform(params.get("platform", ["auto"])[0]),
            own_site_url=params.get("own_site_url", ["https://alphaxxxx.com/"])[0],
            extra_site_urls=extra_urls,
            run_mode=params.get("run_mode", ["quick"])[0],
            selected_models=selected_models,
            recrawl_own_site=params.get("recrawl_own_site", ["0"])[0] == "1",
            rescan_corpus=params.get("rescan_corpus", ["0"])[0] == "1",
            regenerate_scenarios=params.get("regenerate_scenarios", ["0"])[0] == "1",
            sync_aws=params.get("sync_aws", ["0"])[0] == "1",
            sync_run_artifacts=params.get("sync_run_artifacts", ["1"])[0] == "1",
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
        if parsed.path == "/api/server-update":
            self._send_json(handle_server_update_request(project_root=PROJECT_ROOT, params=params))
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
