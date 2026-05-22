from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.client_acquisition_simulator import QUERY_FIELDS


def read_query_rows(seed_run_dir: Path) -> list[dict[str, str]]:
    seed_path = seed_run_dir / "api_queries.csv"
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed queries file not found: {seed_path}")
    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def select_queries_for_model(seed_run_dir: Path, model: str, limit: int | None = None) -> list[dict[str, str]]:
    rows = read_query_rows(seed_run_dir)
    selected = [row for row in rows if row.get("scenario_model") == model]
    if limit is not None:
        selected = selected[:limit]
    return [{field: str(row.get(field, "")) for field in QUERY_FIELDS} for row in selected]


def seed_queries_for_model(seed_run_dir: Path, model: str, output_dir: Path, limit: int | None = None) -> int:
    rows = select_queries_for_model(seed_run_dir, model, limit=limit)
    if not rows:
        raise ValueError(f"No seeded queries found for model {model} in {seed_run_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "api_queries.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUERY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed one model run with existing API-generated queries.")
    parser.add_argument("--seed-run-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    count = seed_queries_for_model(Path(args.seed_run_dir), args.model, Path(args.output_dir), limit=args.limit)
    print(count)


if __name__ == "__main__":
    main()
