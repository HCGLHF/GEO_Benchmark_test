from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.config import CloudConfig
from scripts.cloud.industry import normalize_industry_id
from scripts.cloud.postgres import execute_schema, upsert_industry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "sql" / "001_initial_schema.sql"
DEFAULT_MIGRATIONS = [ROOT / "sql" / "002_industry_isolation.sql"]


def build_industry_record(
    *,
    industry_id: str,
    display_name: str = "",
    region: str = "",
    notes: str = "",
) -> dict[str, str]:
    return {
        "industry_id": normalize_industry_id(industry_id),
        "display_name": display_name.strip(),
        "region": region.strip(),
        "notes": notes.strip(),
    }


def _nullable(value: str) -> str | None:
    clean_value = value.strip()
    return clean_value or None


def create_industry(
    *,
    industry_id: str,
    display_name: str = "",
    region: str = "",
    notes: str = "",
    execute: bool = False,
) -> dict[str, Any]:
    record = build_industry_record(
        industry_id=industry_id,
        display_name=display_name,
        region=region,
        notes=notes,
    )
    if not execute:
        return {"status": "dry_run", "industry": record}

    config = CloudConfig.from_env()
    execute_schema(config.database_url, DEFAULT_SCHEMA)
    for migration_path in DEFAULT_MIGRATIONS:
        if migration_path.exists():
            execute_schema(config.database_url, migration_path)
    upsert_industry(
        config.database_url,
        industry_id=record["industry_id"],
        display_name=_nullable(record["display_name"]),
        region=_nullable(record["region"]),
        notes=_nullable(record["notes"]),
    )
    return {"status": "upserted", "industry": record}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a cloud industry registry row.")
    parser.add_argument("--industry", required=True, help="Industry id such as geo-agency, dental, or real-estate.")
    parser.add_argument("--display-name", default="", help="Human-readable industry name.")
    parser.add_argument("--region", default="", help="Optional region or market scope.")
    parser.add_argument("--notes", default="", help="Optional notes for the industry registry.")
    parser.add_argument("--execute", action="store_true", help="Actually write the industry row to PostgreSQL.")
    args = parser.parse_args()

    result = create_industry(
        industry_id=args.industry,
        display_name=args.display_name,
        region=args.region,
        notes=args.notes,
        execute=args.execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
