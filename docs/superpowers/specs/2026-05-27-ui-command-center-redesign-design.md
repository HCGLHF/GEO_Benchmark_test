# UI Command Center Redesign Design

## Context

The local GEO Benchmark Console is currently a long two-column page rendered from `scripts/ui_app/server.py`. It exposes read-only dashboard state, report history, owned-page drilldowns, guarded run planning, guarded launch controls, and run monitoring. The current layout works, but it asks the user to scan too many panels at once and makes the main workflows feel equal in priority.

This redesign keeps the standard-library HTTP server and existing API endpoints. It changes the browser UI only: structure, visual hierarchy, interaction affordances, and icon-led controls.

## Goals

- Make the first screen easier to understand: current corpus, latest report, run health, and next actions should be visible without reading every panel.
- Move from a stacked dashboard to a command-center layout with persistent icon navigation.
- Add clear interactions: tab-like workspaces, compact metric cards, status badges, collapsible logs, button loading/disabled states, and safer action feedback.
- Add inline SVG icons for navigation, metrics, buttons, and status surfaces without adding external dependencies.
- Preserve all existing safety boundaries around generated commands, API launches, pipeline launches, stop, and resume.

## Non-Goals

- Do not add React, Vite, FastAPI, or a build step.
- Do not change API execution, cloud sync, crawler, evaluator, report, or monitor semantics.
- Do not add arbitrary file browsing, arbitrary command execution, raw pid control, or broader report preview access.
- Do not redesign the external Cloudflare Access deployment path.

## Recommended Direction

Use the selected Command Center direction:

- A fixed left rail with icon buttons for Overview, Run Setup, Monitor, Reports, Pages, Cloud, and Commands.
- A top header for product identity, active workspace title, refresh action, and global run status.
- A main content area that shows one workspace at a time while keeping the most important overview metrics prominent.
- Compact, operational visual style: light canvas, white panels, dark rail, teal action accent, amber/red warning states, and restrained borders.

## Architecture

All implementation stays in `scripts/ui_app/server.py` inside the existing `HTML` string unless a small extraction is needed for clarity. The Python request handlers and state-building modules remain unchanged except for test-driven adjustments if the UI needs an additional read-only field that already exists in backend state.

Client-side JavaScript keeps using the current fetch endpoints:

- `/api/state`
- `/api/report-history`
- `/api/report-preview`
- `/api/page-drilldown`
- `/api/run-plan`
- `/api/run-monitor`
- `/api/launch-run`
- `/api/launch-stage`
- `/api/stop-run`
- `/api/resume-run`

The page state should be reorganized around a `currentView` value. Navigation buttons update `currentView`, set the active rail item, and show the matching workspace panel. Existing functions such as `loadState`, `buildPlan`, `refreshMonitor`, and report preview loaders should be reused.

## Components

- `app-shell`: fixed rail plus content column.
- `rail-button`: icon-only button with accessible label and title.
- `topbar`: current workspace title, refresh button, auto-refresh indicator, and latest monitor health badge.
- `metric-card`: icon, numeric value, label, and optional status tone.
- `workspace`: hidden/shown panel for Overview, Run Setup, Monitor, Reports, Pages, Cloud, and Commands.
- `action-row`: primary and secondary action buttons with icons and status text.
- `status-badge`: ok, warning, danger, muted, and active states.
- `log-panel`: collapsible log/command preview areas using existing `<pre>` content.
- `data-table`: existing report, model, stage, and page tables with improved spacing and scroll behavior.

## Data Flow

1. `loadState()` fetches `/api/state`, stores `state`, renders overview metrics, models, competitors, cloud rows, report history, and latest drilldown.
2. Form changes still call `buildPlan()`, which updates command preview, warnings, and guarded stage choices.
3. Report history selections still call `loadReportPreview()` and `loadPageDrilldown()`, then hand off the monitor root when present.
4. Monitor refresh still calls `/api/run-monitor` and updates model/stage tables, health, report metrics, and log content.
5. Launch, stage launch, stop, and resume keep their existing browser confirmation gates and server-side command regeneration.

## Error Handling And Safety

- Failed fetches should render a compact error notice in the active workspace instead of silently leaving stale content.
- Destructive or cost-bearing actions keep the existing `window.confirm` / `window.prompt` gates.
- Primary action buttons should show a pending label and be temporarily disabled while their request is in flight.
- Warnings from run plans remain visually prominent and should not be hidden inside collapsed panels by default.
- Report previews and page drilldowns remain restricted to known completed report directories under `runs/`.
- Stop/resume controls remain tied to trusted UI launch manifests through backend validation.

## Accessibility

- Icon-only controls need `aria-label` and `title`.
- Active navigation state should be indicated visually and with `aria-current="page"`.
- Buttons must retain visible focus outlines.
- Status colors must be paired with text labels, not color alone.
- Tables should keep readable headers and horizontal scroll containers on narrow screens.

## Testing

- Update existing UI HTML tests to cover the new shell, rail buttons, icon labels, view panels, and preserved safety text.
- Keep existing endpoint/unit tests unchanged unless the implementation needs additional read-only state.
- Run focused UI tests first, then the broader test suite if the edit touches shared rendering or monitor behavior.
- Start the local UI server and verify in the browser that the first screen is nonblank, navigation switches panels, run-plan changes still update commands, report selection still loads previews/drilldowns, and monitor refresh still renders tables/logs.

## Rollout

This is a local UI-only redesign. It can ship as one scoped change after tests and browser verification. No data migration or service config change is required.
