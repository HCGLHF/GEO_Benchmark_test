# UI Command Center Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the local GEO Benchmark Console into a simpler command-center UI with icon navigation, clearer workspace interactions, and preserved guarded execution safety.

**Architecture:** Keep the standard-library UI server and existing endpoints. Rework only the embedded `HTML` string in `scripts/ui_app/server.py`, using static HTML/CSS/vanilla JS with inline SVG icons and client-side workspace switching.

**Tech Stack:** Python stdlib HTTP server, embedded HTML/CSS/JavaScript, pytest, in-app browser verification.

---

## File Structure

- Modify: `tests/test_ui_dashboard.py`
  - Owns embedded HTML regression checks for shell structure, icons, workspaces, progress UI, report history, owned-page drilldown, and safety controls.
- Modify: `tests/test_ui_run_plan.py`
  - Keeps existing embedded form and stage-command checks passing after markup moves into the Run Setup workspace.
- Modify: `scripts/ui_app/server.py`
  - Replaces the long two-column HTML layout with a command-center shell.
  - Keeps all existing endpoint handlers and server-side safety validation unchanged.
- Modify: `docs/ui-console.md`
  - Documents the new command-center navigation and unchanged safety boundaries.
- Modify: `docs/next.md`
  - Records completed UI redesign work, learned constraints, residual risks, and next follow-ups.

## Task 1: Add Shell And Navigation HTML Tests

**Files:**
- Modify: `tests/test_ui_dashboard.py`
- Test: `tests/test_ui_dashboard.py`

- [ ] **Step 1: Add failing command-center shell assertions**

Add this test after `test_ui_html_constrains_code_blocks_inside_grid`:

```python
def test_ui_html_renders_command_center_shell() -> None:
    assert 'class="app-shell"' in HTML
    assert 'class="nav-rail"' in HTML
    assert 'data-view-target="overview"' in HTML
    assert 'data-view-target="run-setup"' in HTML
    assert 'data-view-target="monitor"' in HTML
    assert 'data-view-target="reports"' in HTML
    assert 'data-view-target="pages"' in HTML
    assert 'data-view-target="cloud"' in HTML
    assert 'data-view-target="commands"' in HTML
    assert 'aria-label="Overview"' in HTML
    assert 'aria-label="Run setup"' in HTML
    assert 'aria-label="Run monitor"' in HTML
    assert 'aria-current="page"' in HTML
```

- [ ] **Step 2: Add failing icon and workspace assertions**

Add this test after the shell test:

```python
def test_ui_html_renders_icons_and_workspaces() -> None:
    assert 'class="icon icon-overview"' in HTML
    assert 'class="icon icon-run"' in HTML
    assert 'class="icon icon-monitor"' in HTML
    assert 'class="workspace active" data-view="overview"' in HTML
    assert 'class="workspace" data-view="run-setup"' in HTML
    assert 'class="workspace" data-view="monitor"' in HTML
    assert 'id="globalHealthBadge"' in HTML
    assert 'id="activeWorkspaceTitle"' in HTML
```

- [ ] **Step 3: Run the focused tests and verify failure**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_renders_command_center_shell tests\test_ui_dashboard.py::test_ui_html_renders_icons_and_workspaces -q
```

Expected: both tests fail because the current HTML still uses `header`, `main`, and `.stack` without the new shell, rail, and workspace markers.

## Task 2: Implement Command-Center CSS And Static Shell

**Files:**
- Modify: `scripts/ui_app/server.py`
- Test: `tests/test_ui_dashboard.py`

- [ ] **Step 1: Replace top-level layout CSS**

Inside the `<style>` block in `scripts/ui_app/server.py`, replace the current `body`, `header`, `main`, `section`, `.stack`, `.button`, `.metric`, and related layout rules with command-center rules that include these selectors:

```css
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
.content-shell {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.topbar {
  min-width: 0;
  padding: 18px 24px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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
.button.secondary { background: #344054; }
.button.ghost {
  color: var(--ink);
  background: #eef2f7;
}
.button.danger { background: var(--danger); }
.button:disabled {
  opacity: 0.62;
  cursor: wait;
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
}
.status-badge.ok { color: var(--ok); background: #ecfdf3; border-color: #abefc6; }
.status-badge.warning { color: var(--warn); background: #fff7ed; border-color: #fed7aa; }
.status-badge.error { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
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
  .metrics, .row, .checks { grid-template-columns: 1fr; }
  .topbar { align-items: flex-start; flex-direction: column; }
}
```

Preserve the existing detailed rules for inputs, checkboxes, lists, pills, progress bars, tables, `.table-scroll`, `.owned-pages-table`, `.url-cell`, `.metric-cell`, `.hint-cell`, warnings, and `<pre>`.

- [ ] **Step 2: Replace body markup with rail and workspaces**

Replace the current `<header>` and `<main>` body markup with this structure, keeping all existing element ids inside the new workspace panels:

```html
<div class="app-shell">
  <aside class="nav-rail" aria-label="Primary">
    <div class="rail-brand" title="GEO Benchmark Console">G</div>
    <nav class="rail-nav" aria-label="Workspaces">
      <button class="rail-button active" data-view-target="overview" aria-label="Overview" aria-current="page" title="Overview"><svg class="icon icon-overview" viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg></button>
      <button class="rail-button" data-view-target="run-setup" aria-label="Run setup" title="Run setup"><svg class="icon icon-run" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button>
      <button class="rail-button" data-view-target="monitor" aria-label="Run monitor" title="Run monitor"><svg class="icon icon-monitor" viewBox="0 0 24 24"><path d="M4 19V5M4 19h16M8 15v-4M12 15V7M16 15v-6"/></svg></button>
      <button class="rail-button" data-view-target="reports" aria-label="Reports" title="Reports"><svg class="icon icon-reports" viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7zM14 3v5h5M9 14h8M9 18h6"/></svg></button>
      <button class="rail-button" data-view-target="pages" aria-label="Owned pages" title="Owned pages"><svg class="icon icon-pages" viewBox="0 0 24 24"><path d="M4 5h16v14H4zM8 9h8M8 13h5M8 17h7"/></svg></button>
      <button class="rail-button" data-view-target="cloud" aria-label="Cloud store" title="Cloud store"><svg class="icon icon-cloud" viewBox="0 0 24 24"><path d="M17 18H7a4 4 0 1 1 .8-7.9A5.5 5.5 0 0 1 18.4 12 3 3 0 0 1 17 18z"/></svg></button>
      <button class="rail-button" data-view-target="commands" aria-label="Commands" title="Commands"><svg class="icon icon-commands" viewBox="0 0 24 24"><path d="M4 17l5-5-5-5M12 19h8"/></svg></button>
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
        <!-- Resource Library, Latest Report, Competitors, and compact next-action panels move here. -->
      </section>
      <section class="workspace" data-view="run-setup">
        <!-- Run Setup form, model list, launch controls, and stage selector move here. -->
      </section>
      <section class="workspace" data-view="monitor">
        <!-- Run Monitor controls, metrics, tables, and logs move here. -->
      </section>
      <section class="workspace" data-view="reports">
        <!-- Report History and Report Preview move here. -->
      </section>
      <section class="workspace" data-view="pages">
        <!-- Owned Page Drilldown tables move here. -->
      </section>
      <section class="workspace" data-view="cloud">
        <!-- Cloud Store table moves here. -->
      </section>
      <section class="workspace" data-view="commands">
        <!-- Dry Run Commands and warnings move here. -->
      </section>
    </main>
  </div>
</div>
```

When filling the comments, move the existing panels without renaming ids such as `companyCount`, `reportHistoryTable`, `runMode`, `stageCommand`, `commands`, `warnings`, `monitorModelsTable`, and `monitorLog`.

- [ ] **Step 3: Run shell tests**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_renders_command_center_shell tests\test_ui_dashboard.py::test_ui_html_renders_icons_and_workspaces -q
```

Expected: `2 passed`.

- [ ] **Step 4: Commit shell work**

Run:

```powershell
git add tests\test_ui_dashboard.py scripts\ui_app\server.py
git commit -m "feat: add command center UI shell"
```

Expected: commit succeeds and only the test file plus `scripts/ui_app/server.py` are included.

## Task 3: Add Workspace Switching And Status Interaction

**Files:**
- Modify: `tests/test_ui_dashboard.py`
- Modify: `scripts/ui_app/server.py`
- Test: `tests/test_ui_dashboard.py`

- [ ] **Step 1: Add failing JavaScript interaction assertions**

Add this test near the other embedded HTML tests:

```python
def test_ui_html_switches_command_center_workspaces() -> None:
    assert "const workspaceTitles" in HTML
    assert "function setCurrentView" in HTML
    assert "document.querySelectorAll(\"[data-view-target]\")" in HTML
    assert "button.setAttribute(\"aria-current\", \"page\")" in HTML
    assert "workspace.classList.toggle(\"active\", workspace.dataset.view === view)" in HTML
    assert "localStorage.setItem(\"geo.currentView\", view)" in HTML
```

Add this test below it:

```python
def test_ui_html_updates_global_health_badge() -> None:
    assert "function setGlobalHealth" in HTML
    assert "globalHealthBadge" in HTML
    assert "globalHealthBadge.className = `status-badge ${tone}`" in HTML
    assert "setGlobalHealth(health.status)" in HTML
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_switches_command_center_workspaces tests\test_ui_dashboard.py::test_ui_html_updates_global_health_badge -q
```

Expected: both tests fail because workspace switching and global health badge helpers do not exist yet.

- [ ] **Step 3: Add workspace switching JavaScript**

At the start of the `<script>` block, after `let lastPlan = null;`, add:

```javascript
    const workspaceTitles = {
      overview: "Overview",
      "run-setup": "Run Setup",
      monitor: "Run Monitor",
      reports: "Reports",
      pages: "Owned Pages",
      cloud: "Cloud Store",
      commands: "Commands",
    };

    function setCurrentView(view) {
      const nextView = workspaceTitles[view] ? view : "overview";
      document.querySelectorAll("[data-view-target]").forEach((button) => {
        const active = button.dataset.viewTarget === nextView;
        button.classList.toggle("active", active);
        if (active) {
          button.setAttribute("aria-current", "page");
        } else {
          button.removeAttribute("aria-current");
        }
      });
      document.querySelectorAll(".workspace").forEach((workspace) => {
        workspace.classList.toggle("active", workspace.dataset.view === nextView);
      });
      byId("activeWorkspaceTitle").textContent = workspaceTitles[nextView];
      localStorage.setItem("geo.currentView", nextView);
    }
```

- [ ] **Step 4: Add global health badge helper**

Below `setCurrentView`, add:

```javascript
    function setGlobalHealth(status) {
      const value = String(status || "unknown");
      let tone = "";
      if (["ok", "complete", "completed"].includes(value)) tone = "ok";
      if (["warning", "complete_with_model_warnings", "interrupted"].includes(value)) tone = "warning";
      if (["error", "failed"].includes(value)) tone = "error";
      byId("globalHealthBadge").className = `status-badge ${tone}`;
      byId("globalHealthBadge").textContent = value.replaceAll("_", " ");
    }
```

Inside `refreshMonitor()`, after `const health = monitor.health || ...`, add:

```javascript
      setGlobalHealth(health.status);
```

At the bottom of the script, before `loadState().then(refreshMonitor);`, add:

```javascript
    document.querySelectorAll("[data-view-target]").forEach((button) => {
      button.addEventListener("click", () => setCurrentView(button.dataset.viewTarget));
    });
    setCurrentView(localStorage.getItem("geo.currentView") || "overview");
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_switches_command_center_workspaces tests\test_ui_dashboard.py::test_ui_html_updates_global_health_badge -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit workspace interactions**

Run:

```powershell
git add tests\test_ui_dashboard.py scripts\ui_app\server.py
git commit -m "feat: switch UI workspaces from icon rail"
```

Expected: commit succeeds.

## Task 4: Add Safer Action Feedback And Collapsible Logs

**Files:**
- Modify: `tests/test_ui_dashboard.py`
- Modify: `scripts/ui_app/server.py`
- Test: `tests/test_ui_dashboard.py`

- [ ] **Step 1: Add failing feedback tests**

Add this test near the action-control tests:

```python
def test_ui_html_renders_action_feedback_and_collapsible_logs() -> None:
    assert "async function withButtonBusy" in HTML
    assert "button.disabled = true" in HTML
    assert "button.dataset.originalText" in HTML
    assert "class=\"log-toggle\"" in HTML
    assert "data-log-target=\"monitorLog\"" in HTML
    assert "function toggleLogPanel" in HTML
    assert "setNotice(\"launchStatus\"" in HTML
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_renders_action_feedback_and_collapsible_logs -q
```

Expected: the test fails because busy-state and log-toggle helpers do not exist yet.

- [ ] **Step 3: Add log toggle markup**

In the Commands workspace, wrap `commands` with a toggle:

```html
<button class="log-toggle" type="button" data-log-target="commands">Command preview</button>
<pre id="commands"></pre>
```

In the Monitor workspace, wrap `monitorLog` with a toggle:

```html
<button class="log-toggle" type="button" data-log-target="monitorLog">Monitor logs</button>
<pre id="monitorLog"></pre>
```

- [ ] **Step 4: Add feedback JavaScript helpers**

After `escapeHtml`, add:

```javascript
    function setNotice(id, message, tone = "") {
      const node = byId(id);
      node.className = tone ? `notice ${tone}` : "muted";
      node.textContent = message || "";
    }

    async function withButtonBusy(button, busyText, action) {
      button.dataset.originalText = button.textContent;
      button.disabled = true;
      button.textContent = busyText;
      try {
        return await action();
      } finally {
        button.disabled = false;
        button.textContent = button.dataset.originalText;
      }
    }

    function toggleLogPanel(targetId) {
      const target = byId(targetId);
      target.hidden = !target.hidden;
    }
```

Add CSS:

```css
.notice {
  border-radius: 7px;
  border: 1px solid var(--line);
  padding: 9px 10px;
  font-size: 13px;
  background: #fff;
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
```

- [ ] **Step 5: Use busy helper for guarded actions**

Change button event listeners from direct calls to busy wrappers:

```javascript
    byId("launchApi").addEventListener("click", () => withButtonBusy(byId("launchApi"), "Launching...", launchApiRun));
    byId("launchStage").addEventListener("click", () => withButtonBusy(byId("launchStage"), "Launching...", launchStage));
    byId("monitorRefresh").addEventListener("click", () => withButtonBusy(byId("monitorRefresh"), "Refreshing...", refreshMonitor));
    byId("stopApiRun").addEventListener("click", () => withButtonBusy(byId("stopApiRun"), "Stopping...", stopApiRun));
    byId("resumeApiRun").addEventListener("click", () => withButtonBusy(byId("resumeApiRun"), "Resuming...", resumeApiRun));
    document.querySelectorAll("[data-log-target]").forEach((button) => {
      button.addEventListener("click", () => toggleLogPanel(button.dataset.logTarget));
    });
```

In `launchApiRun()`, replace direct launch-status writes with:

```javascript
      setNotice("launchStatus", `${launch.status}: pid ${launch.pid || "-"} - monitor ${launch.monitor_run_root || ""}`, "ok");
```

In error branches, use:

```javascript
      setNotice("launchStatus", "No guarded pipeline step is available in the current plan.", "warning");
```

- [ ] **Step 6: Run focused test**

Run:

```powershell
pytest tests\test_ui_dashboard.py::test_ui_html_renders_action_feedback_and_collapsible_logs -q
```

Expected: `1 passed`.

- [ ] **Step 7: Commit feedback interactions**

Run:

```powershell
git add tests\test_ui_dashboard.py scripts\ui_app\server.py
git commit -m "feat: add UI action feedback"
```

Expected: commit succeeds.

## Task 5: Preserve Existing UI Contracts

**Files:**
- Modify: `tests/test_ui_dashboard.py`
- Modify: `tests/test_ui_run_plan.py`
- Modify: `scripts/ui_app/server.py`
- Test: `tests/test_ui_dashboard.py`, `tests/test_ui_run_plan.py`

- [ ] **Step 1: Update old layout assertions to new shell**

Replace `test_ui_html_constrains_code_blocks_inside_grid` with:

```python
def test_ui_html_constrains_code_blocks_inside_grid() -> None:
    assert ".content-shell" in HTML
    assert ".workspace-wrap" in HTML
    assert ".panel {" in HTML
    assert "min-width: 0;" in HTML
    assert "overflow-wrap: anywhere;" in HTML
```

- [ ] **Step 2: Confirm all old ids and endpoint strings remain**

Run:

```powershell
pytest tests\test_ui_dashboard.py tests\test_ui_run_plan.py -q
```

Expected: all tests in both files pass. If a failure names a missing id such as `monitorAutoRefresh`, `stageCommand`, `reportPreview`, `ownedTopPagesTable`, or `platform`, move that original element into the relevant workspace without renaming it.

- [ ] **Step 3: Commit preserved contracts**

Run:

```powershell
git add tests\test_ui_dashboard.py tests\test_ui_run_plan.py scripts\ui_app\server.py
git commit -m "test: preserve UI command center contracts"
```

Expected: commit succeeds.

## Task 6: Browser Verification And Documentation

**Files:**
- Modify: `docs/ui-console.md`
- Modify: `docs/next.md`
- Test: local UI server and browser

- [ ] **Step 1: Start the local UI server**

Run:

```powershell
python -m scripts.ui_app.server --host 127.0.0.1 --port 8765
```

Expected: terminal prints `GEO Benchmark Console: http://127.0.0.1:8765`.

- [ ] **Step 2: Verify the browser flow**

Open `http://127.0.0.1:8765` in the in-app browser and verify:

- Overview loads with resource-library and latest-report metrics.
- Icon rail switches to Run Setup, Monitor, Reports, Pages, Cloud, and Commands.
- Changing run mode or checkboxes still updates Dry Run Commands.
- Report History `Open` loads preview and page drilldown.
- Run Monitor refresh renders model/stage tables or a readable error for a missing run root.
- Guarded API/stage/stop/resume buttons still show confirmation before any request that can mutate state or spend API credits.

- [ ] **Step 3: Document the command-center navigation**

In `docs/ui-console.md`, add this under `## Current Capabilities`:

```markdown
- Uses a command-center layout with icon navigation for Overview, Run Setup, Run Monitor, Reports, Owned Pages, Cloud Store, and Dry Run Commands.
- Shows action feedback for guarded launches, stop/resume requests, and monitor refreshes while preserving the existing confirmation gates.
```

- [ ] **Step 4: Update project memory**

In `docs/next.md`, add to `## Done`:

```markdown
- Redesigned the local UI console into a command-center layout with icon navigation, workspace switching, compact status surfaces, action feedback, and collapsible command/log panels.
```

Add to `## Learned`:

```markdown
- The local UI can gain clearer interaction and visual hierarchy without changing the standard-library server or guarded execution endpoints.
```

Add to `## Risks`:

```markdown
- Icon-only navigation must keep accessible labels and visible active state, otherwise the simpler layout becomes harder to operate for keyboard and screen-reader users.
```

Add to `## Next`:

```markdown
1. Add launch-history detail inside the Monitor workspace so users can see which UI launch or resume attempt produced the current run root.
```

If `docs/next.md` already has numbered items, insert the new next item near the existing UI launch-history item and renumber only the affected list.

- [ ] **Step 5: Run focused verification**

Run:

```powershell
pytest tests\test_ui_dashboard.py tests\test_ui_run_plan.py tests\test_ui_run_monitor.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Run full verification if focused tests pass**

Run:

```powershell
pytest
```

Expected: all tests pass. If the full suite is too slow for the session, record the focused test result and the reason full verification was not run.

- [ ] **Step 7: Commit final docs and verification fixes**

Run:

```powershell
git add scripts\ui_app\server.py tests\test_ui_dashboard.py tests\test_ui_run_plan.py docs\ui-console.md docs\next.md
git commit -m "docs: update UI command center notes"
```

Expected: commit succeeds with only UI, tests, and docs changes.
