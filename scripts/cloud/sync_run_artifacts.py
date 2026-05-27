from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._common import utc_now_iso
from scripts.cloud.config import CloudConfig
from scripts.cloud.industry import normalize_industry_id
from scripts.cloud.postgres import register_artifact_objects
from scripts.cloud.s3_artifacts import sha256_file, upload_artifact


MERGED_PREFERENCE = ("merged", "merged_with_page_drilldown", "merged_3_models")
RUN_ROOT_FILES = {
    "run_manifest.json": ("run_manifest", "manifest"),
    "pipeline_state.jsonl": ("pipeline_state", "logs"),
    "progress.html": ("progress_html", "ui"),
}
MERGED_FILES = {
    "merge_manifest.json": ("merge_manifest", "manifest"),
    "competitive_gap_report.md": ("competitive_gap_report", "reports"),
    "brand_performance_by_model.csv": ("brand_performance_by_model", "tables"),
    "dimension_breakdown.csv": ("dimension_breakdown", "tables"),
    "retrieval_by_model.csv": ("retrieval_by_model", "tables"),
    "model_answer_evaluations.csv": ("model_answer_evaluations", "tables"),
    "api_call_summary.csv": ("api_call_summary", "tables"),
    "query_loss_analysis.csv": ("query_loss_analysis", "tables"),
    "competitor_displacements.csv": ("competitor_displacements", "tables"),
    "page_optimization_plan.csv": ("page_optimization_plan", "tables"),
    "url_top5_rankings.csv": ("url_top5_rankings", "tables"),
    "domain_top5_rankings.csv": ("domain_top5_rankings", "tables"),
    "persona_stage_losses.csv": ("persona_stage_losses", "tables"),
    "page_intent_weakness.csv": ("page_intent_weakness", "tables"),
    "content_optimization_actions.csv": ("content_optimization_actions", "tables"),
    "report_deep_diagnostics.json": ("report_deep_diagnostics", "json"),
    "owned_top5_pages.csv": ("owned_top5_pages", "tables"),
    "owned_weak_pages.csv": ("owned_weak_pages", "tables"),
    "retrieval_evidence_by_model.jsonl": ("retrieval_evidence_by_model", "jsonl"),
}


@dataclass(frozen=True)
class RunReport:
    run_root: Path
    run_mode: str
    merged_dir: Path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _candidate_run_roots(roots: list[Path]) -> list[Path]:
    candidates: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        if _preferred_merged_dir(root) is not None:
            candidates.add(root)
            continue
        for child in root.iterdir():
            if child.is_dir() and _preferred_merged_dir(child) is not None:
                candidates.add(child)
    return sorted(candidates, key=lambda path: path.name)


def _merged_dirs(run_root: Path) -> list[Path]:
    dirs = [
        path
        for path in run_root.iterdir()
        if path.is_dir() and path.name.startswith("merged") and (path / "competitive_gap_report.md").exists()
    ]
    preference = {name: index for index, name in enumerate(MERGED_PREFERENCE)}
    return sorted(dirs, key=lambda path: (preference.get(path.name, 99), path.name))


def _preferred_merged_dir(run_root: Path) -> Path | None:
    dirs = _merged_dirs(run_root) if run_root.exists() else []
    return dirs[0] if dirs else None


def _mode_from_legacy_counts(merged_dir: Path) -> str | None:
    manifest = _read_json(merged_dir / "merge_manifest.json")
    result = manifest.get("result") if isinstance(manifest.get("result"), dict) else {}
    source_count = int(result.get("source_run_count") or len(manifest.get("source_runs") or []) or 0)
    query_rows = int(result.get("query_rows") or 0)
    if source_count <= 0 or query_rows <= 0:
        return None
    queries_per_model = query_rows / source_count
    if queries_per_model <= 2:
        return "test"
    if queries_per_model <= 50:
        return "quick"
    if queries_per_model >= 200:
        return "standard"
    return None


def infer_run_mode(run_root: Path, merged_dir: Path) -> str | None:
    manifest = _read_json(run_root / "run_manifest.json")
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    mode = str(metadata.get("run_mode") or "").strip().lower()
    if mode:
        return mode
    if "quick" in str(run_root).lower().replace("\\", "/"):
        return "quick"
    return _mode_from_legacy_counts(merged_dir)


def _is_failed(run_root: Path) -> bool:
    manifest = _read_json(run_root / "run_manifest.json")
    return str(manifest.get("status") or "").lower() == "failed"


def discover_run_reports(run_roots: list[Path], run_modes: set[str]) -> list[RunReport]:
    reports: list[RunReport] = []
    normalized_modes = {mode.lower() for mode in run_modes}
    for run_root in _candidate_run_roots(run_roots):
        if _is_failed(run_root):
            continue
        merged_dir = _preferred_merged_dir(run_root)
        if merged_dir is None:
            continue
        run_mode = infer_run_mode(run_root, merged_dir)
        if run_mode in normalized_modes:
            reports.append(RunReport(run_root=run_root, run_mode=run_mode, merged_dir=merged_dir))
    return reports


def discover_run_roots(run_roots: list[Path], run_modes: set[str]) -> list[Path]:
    return [report.run_root for report in discover_run_reports(run_roots, run_modes)]


def _run_object_key(
    *,
    industry_id: str,
    corpus_version: str,
    run_mode: str,
    run_id: str,
    section: str,
    filename: str,
) -> str:
    clean_industry = normalize_industry_id(industry_id)
    return f"industries/{clean_industry}/runs/{corpus_version}/{run_mode}/{run_id}/{section}/{filename}"


def _artifact_record(
    *,
    industry_id: str,
    corpus_version: str,
    artifact_type: str,
    source_path: Path,
    object_key: str,
) -> dict[str, Any]:
    clean_industry = normalize_industry_id(industry_id)
    return {
        "industry_id": clean_industry,
        "corpus_version": corpus_version,
        "artifact_type": artifact_type,
        "object_key": object_key,
        "sha256": sha256_file(source_path),
        "size_bytes": source_path.stat().st_size,
        "source_path": str(source_path),
        "created_at": utc_now_iso(),
    }


def build_run_artifact_plan(
    *,
    industry_id: str,
    corpus_version: str,
    run_root: Path,
    run_mode: str,
    merged_dir: Path,
) -> dict[str, Any]:
    run_id = run_root.name
    artifacts: list[dict[str, Any]] = []
    for filename, (artifact_type, section) in RUN_ROOT_FILES.items():
        source_path = run_root / filename
        if source_path.exists():
            artifacts.append(
                _artifact_record(
                    industry_id=industry_id,
                    corpus_version=corpus_version,
                    artifact_type=artifact_type,
                    source_path=source_path,
                    object_key=_run_object_key(
                        industry_id=industry_id,
                        corpus_version=corpus_version,
                        run_mode=run_mode,
                        run_id=run_id,
                        section=section,
                        filename=filename,
                    ),
                )
            )
    for filename, (artifact_type, section) in MERGED_FILES.items():
        source_path = merged_dir / filename
        if source_path.exists():
            artifacts.append(
                _artifact_record(
                    industry_id=industry_id,
                    corpus_version=corpus_version,
                    artifact_type=artifact_type,
                    source_path=source_path,
                    object_key=_run_object_key(
                        industry_id=industry_id,
                        corpus_version=corpus_version,
                        run_mode=run_mode,
                        run_id=run_id,
                        section=section,
                        filename=filename,
                    ),
                )
            )
    return {
        "industry_id": normalize_industry_id(industry_id),
        "corpus_version": corpus_version,
        "run_root": str(run_root),
        "run_mode": run_mode,
        "merged_dir": str(merged_dir),
        "artifacts": artifacts,
    }


def _summary(plans: list[dict[str, Any]]) -> dict[str, Any]:
    artifact_count = sum(len(plan["artifacts"]) for plan in plans)
    size_bytes = sum(int(artifact["size_bytes"]) for plan in plans for artifact in plan["artifacts"])
    return {"run_count": len(plans), "artifact_count": artifact_count, "size_bytes": size_bytes}


def run_sync(
    *,
    industry_id: str,
    corpus_version: str,
    run_roots: list[Path],
    run_modes: set[str],
    execute: bool = False,
    skip_s3: bool = False,
    skip_db: bool = False,
    upload_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    register_fn: Callable[[list[dict[str, Any]]], None] | None = None,
) -> dict[str, Any]:
    reports = discover_run_reports(run_roots, run_modes)
    plans = [
        build_run_artifact_plan(
            industry_id=industry_id,
            corpus_version=corpus_version,
            run_root=report.run_root,
            run_mode=report.run_mode,
            merged_dir=report.merged_dir,
        )
        for report in reports
    ]
    result = {
        "status": "dry_run",
        "industry_id": normalize_industry_id(industry_id),
        "corpus_version": corpus_version,
        "summary": _summary(plans),
        "plans": plans,
    }
    if not execute:
        return result

    needs_config = (not skip_s3 and upload_fn is None) or (not skip_db and register_fn is None)
    config = CloudConfig.from_env() if needs_config else None
    uploaded_records: list[dict[str, Any]] = []
    for plan in plans:
        for artifact in plan["artifacts"]:
            if skip_s3:
                bucket = config.s3_bucket if config else ""
                uploaded_records.append({**artifact, "bucket": bucket})
            elif upload_fn:
                uploaded_records.append(upload_fn(artifact))
            else:
                assert config is not None
                uploaded_records.append(
                    upload_artifact(bucket=config.s3_bucket, region=config.aws_region, record=artifact)
                )
    if not skip_db:
        if register_fn:
            register_fn(uploaded_records)
        else:
            assert config is not None
            register_artifact_objects(config.database_url, uploaded_records)
    return {**result, "status": "synced", "artifacts": uploaded_records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync completed quick/standard run artifacts to S3/RDS.")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--corpus-version", required=True)
    parser.add_argument("--run-root", action="append", required=True)
    parser.add_argument("--run-mode", action="append", choices=["quick", "standard"], required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-s3", action="store_true")
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()
    result = run_sync(
        industry_id=args.industry,
        corpus_version=args.corpus_version,
        run_roots=[Path(value) for value in args.run_root],
        run_modes=set(args.run_mode),
        execute=args.execute and not args.dry_run,
        skip_s3=args.skip_s3,
        skip_db=args.skip_db,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
