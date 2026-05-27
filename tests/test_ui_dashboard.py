from pathlib import Path
import json

from scripts.ui_app.dashboard import build_dashboard_state
from scripts.ui_app.server import HTML


def test_build_dashboard_state_combines_project_status(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "config" / "client_acquisition_simulator.yaml").write_text(
        """
campaign:
  target_brand: AlphaXXXX
  target_domain: alphaxxxx.com
  competitors:
    - HornTech
models:
  - provider: openrouter
    model: openai/gpt-4.1-mini
""",
        encoding="utf-8",
    )
    (tmp_path / "data" / "processed" / "documents.jsonl").write_text(
        '{"document_id":"doc-a","url":"https://alphaxxxx.com/","brand":"AlphaXXXX"}\n',
        encoding="utf-8",
    )

    state = build_dashboard_state(tmp_path)

    assert state["options"]["target_brand"] == "AlphaXXXX"
    assert state["corpus"]["document_count"] == 1
    assert state["report"]["report_dir"] is None
    assert state["report_history"] == []
    assert state["cloud"]["bucket"] is None
    assert state["cloud"]["rds_endpoint"] is None
    assert state["deployment"]["default_corpus_version"] == "2026-05-27-alpha-refresh"
    assert state["deployment"]["last_deployment"]["status"] == "missing"


def test_build_dashboard_state_loads_non_secret_cloud_status_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    for key in (
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "S3_BUCKET",
        "GEO_S3_BUCKET",
        "DATABASE_URL",
        "GEO_POSTGRES_HOST",
        "GEO_POSTGRES_PASSWORD",
        "AWS_ACCESS_KEY_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "AWS_REGION=ap-northeast-1",
                "S3_BUCKET=geo-resource-library-prod",
                "DATABASE_URL=postgresql://user:secret@geo-postgres-prod.example.com:5432/postgres",
                "AWS_ACCESS_KEY_ID=example-key",
            ]
        ),
        encoding="utf-8",
    )

    state = build_dashboard_state(tmp_path)

    assert state["cloud"]["bucket"] == "geo-resource-library-prod"
    assert state["cloud"]["rds_endpoint"] == "geo-postgres-prod.example.com"
    assert state["cloud"]["aws_region"] == "ap-northeast-1"
    assert state["cloud"]["has_aws_access_key"] is True
    assert state["cloud"]["has_postgres_password"] is True


def test_build_dashboard_state_returns_latest_monitor_run_root(tmp_path: Path) -> None:
    old_launch = tmp_path / "runs" / "ui_launches" / "20260523_010000" / "launch_manifest.json"
    new_launch = tmp_path / "runs" / "ui_launches" / "20260523_040450" / "launch_manifest.json"
    old_launch.parent.mkdir(parents=True)
    new_launch.parent.mkdir(parents=True)
    old_launch.write_text(
        json.dumps({"monitor_run_root": "runs/full_api_parallel_ui/20260523_010000"}),
        encoding="utf-8",
    )
    new_launch.write_text(
        json.dumps({"monitor_run_root": "runs/full_api_parallel_ui/20260523_040450"}),
        encoding="utf-8",
    )

    state = build_dashboard_state(tmp_path)

    assert state["latest_monitor_run_root"] == "runs/full_api_parallel_ui/20260523_040450"


def test_build_dashboard_state_skips_failed_latest_monitor_run_root(tmp_path: Path) -> None:
    old_launch = tmp_path / "runs" / "ui_launches" / "20260523_010000" / "launch_manifest.json"
    failed_launch = tmp_path / "runs" / "ui_launches" / "20260523_040450" / "launch_manifest.json"
    old_launch.parent.mkdir(parents=True)
    failed_launch.parent.mkdir(parents=True)
    old_launch.write_text(
        json.dumps({"status": "launched", "monitor_run_root": "runs/full_api_parallel_ui/20260523_010000"}),
        encoding="utf-8",
    )
    failed_launch.write_text(
        json.dumps({"status": "failed", "monitor_run_root": "runs/full_api_parallel_ui/20260523_040450"}),
        encoding="utf-8",
    )

    state = build_dashboard_state(tmp_path)

    assert state["latest_monitor_run_root"] == "runs/full_api_parallel_ui/20260523_010000"


def test_build_dashboard_state_skips_failed_run_manifest_even_when_launch_is_stale(tmp_path: Path) -> None:
    launch = tmp_path / "runs" / "ui_launches" / "20260523_040450" / "launch_manifest.json"
    launch.parent.mkdir(parents=True)
    launch.write_text(
        json.dumps({"status": "launched", "monitor_run_root": "runs/full_api_parallel_ui/20260523_040450"}),
        encoding="utf-8",
    )
    run_root = tmp_path / "runs" / "full_api_parallel_ui" / "20260523_040450"
    run_root.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")

    state = build_dashboard_state(tmp_path)

    assert state["latest_monitor_run_root"] == ""


def test_ui_html_constrains_code_blocks_inside_grid() -> None:
    assert ".content-shell" in HTML
    assert ".workspace-wrap" in HTML
    assert ".panel {" in HTML
    assert "min-width: 0;" in HTML
    assert "overflow-wrap: anywhere;" in HTML


def test_ui_html_renders_command_center_shell() -> None:
    assert 'class="app-shell"' in HTML
    assert 'class="nav-rail"' in HTML
    assert 'class="rail-brand" title="AlphaXXXX">AX</div>' in HTML
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


def test_ui_html_renders_icons_and_workspaces() -> None:
    assert 'class="icon icon-overview"' in HTML
    assert 'class="icon icon-run"' in HTML
    assert 'class="icon icon-monitor"' in HTML
    assert 'class="workspace active" data-view="overview"' in HTML
    assert 'class="workspace" data-view="run-setup"' in HTML
    assert 'class="workspace" data-view="monitor"' in HTML
    assert 'id="globalHealthBadge"' in HTML
    assert 'id="activeWorkspaceTitle"' in HTML


def test_ui_html_switches_command_center_workspaces() -> None:
    assert "const workspaceTitles" in HTML
    assert "function setCurrentView" in HTML
    assert "document.querySelectorAll(\"[data-view-target]\")" in HTML
    assert "button.setAttribute(\"aria-current\", \"page\")" in HTML
    assert "workspace.classList.toggle(\"active\", workspace.dataset.view === view)" in HTML
    assert "localStorage.setItem(\"geo.currentView\", view)" in HTML


def test_ui_html_updates_global_health_badge() -> None:
    assert "function setGlobalHealth" in HTML
    assert "globalHealthBadge" in HTML
    assert "globalHealthBadge.className = `status-badge ${tone}`" in HTML
    assert "setGlobalHealth(health.status)" in HTML


def test_ui_html_renders_action_feedback_and_collapsible_logs() -> None:
    assert "async function withButtonBusy" in HTML
    assert "button.disabled = true" in HTML
    assert "button.dataset.originalText" in HTML
    assert "class=\"log-toggle\"" in HTML
    assert "data-log-target=\"monitorLog\"" in HTML
    assert "function toggleLogPanel" in HTML
    assert "setNotice(\"launchStatus\"" in HTML


def test_ui_html_renders_pipeline_progress_bars() -> None:
    assert ".progress-track" in HTML
    assert ".progress-fill" in HTML
    assert "renderPipelineProgress" in HTML
    assert "pipeline_progress" in HTML
    assert "monitorAutoRefresh" in HTML
    assert "setInterval" in HTML


def test_ui_html_preserves_selected_pipeline_step_when_rebuilding_plan() -> None:
    assert 'const selectedStageLabel = byId("stageCommand").value;' in HTML
    assert "option.value === selectedStageLabel" in HTML


def test_ui_html_renders_api_progress_and_health() -> None:
    assert '<option value="test">test</option>' in HTML
    assert "renderApiProgress" in HTML
    assert "monitorHealth" in HTML
    assert "health.status" in HTML
    assert "stopApiRun" in HTML
    assert "resumeApiRun" in HTML
    assert "/api/stop-run" in HTML
    assert "/api/resume-run" in HTML


def test_ui_html_restores_latest_monitor_after_refresh() -> None:
    assert "latest_monitor_run_root" in HTML
    assert "geo.monitorRunRoot" in HTML
    assert "setMonitorRunRoot" in HTML
    assert 'const restoredMonitorRoot = state.latest_monitor_run_root || "";' in HTML
    assert "state.latest_monitor_run_root || localStorage.getItem" not in HTML
    assert 'id="monitorRunRoot" type="text" value=""' in HTML
    assert 'id="linkedMonitorRoot" type="text" value=""' in HTML
    assert "full_api_parallel_alpha_refresh_quick_final" not in HTML


def test_ui_html_renders_report_history_and_preview() -> None:
    assert "Report History" in HTML
    assert "Performance Trend" in HTML
    assert "Latest Top 5 Overview" in HTML
    assert "reportTrendChart" in HTML
    assert "latestTopBrands" in HTML
    assert "function renderReportTrendChart" in HTML
    assert "function renderLatestTopBrands" in HTML
    assert "target_model_mention_rate" in HTML
    assert "reportHistoryTable" in HTML
    assert "reportPreview" in HTML
    assert "reportUrlDomainDrilldown" in HTML
    assert "reportPersonaStageDrilldown" in HTML
    assert "reportMoneyPageActions" in HTML
    assert "function renderReportDeepDrilldown" in HTML
    assert "function downloadReport" in HTML
    assert "Download" in HTML
    assert "/api/report-history" in HTML
    assert "/api/report-preview" in HTML
    assert "/api/report-download" in HTML
    assert 'displayHealthStatus(value)' in HTML


def test_ui_html_renders_owned_page_drilldown() -> None:
    assert "Owned Page Drilldown" in HTML
    assert "ownedTopPagesTable" in HTML
    assert "ownedWeakPagesTable" in HTML
    assert "/api/page-drilldown" in HTML


def test_ui_html_renders_deployment_status() -> None:
    assert "Deployment Status" in HTML
    assert "deploymentRows" in HTML
    assert "deploymentStepsTable" in HTML
    assert "runServerUpdate" in HTML
    assert "Run Server Update" in HTML
    assert "function renderDeployment" in HTML
    assert "manual_required" in HTML
    assert "Manual command:" in HTML
    assert 'if (result.status !== "manual_required")' in HTML
    assert "Previous update launcher is stale" in HTML
    assert "renderDeployment(state.deployment)" in HTML
    assert "/api/server-update" in HTML
    assert "git pull, hydrate artifacts, verify cloud import, restart service" in HTML
    assert 'byId("runServerUpdate").disabled = Boolean(updateAction.busy);' in HTML
    assert 'byId("runServerUpdate").addEventListener("click", runServerUpdate);' in HTML


def test_ui_html_constrains_owned_page_tables() -> None:
    assert ".table-scroll" in HTML
    assert ".owned-pages-table" in HTML
    assert "table-layout: fixed;" in HTML
    assert "min-width: 720px;" in HTML
    assert "class=\"url-cell\"" in HTML
    assert "class=\"hint-cell\"" in HTML
