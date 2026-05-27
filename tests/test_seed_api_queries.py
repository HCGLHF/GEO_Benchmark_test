import csv
import subprocess
from pathlib import Path

from scripts.seed_api_queries import seed_queries_for_model


def test_seed_queries_for_model_writes_exact_query_fields_without_bom(tmp_path: Path):
    seed_run = tmp_path / "seed"
    seed_run.mkdir()
    (seed_run / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,query,target_brand,persona,journey_stage,scenario_provider,scenario_model,api_status,notes,extra",
                "q001,Need AI recommendations,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old,x",
                "q002,Need GEO help,AlphaXXXX,owner,aware,openrouter,deepseek/deepseek-chat,success,old,y",
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    count = seed_queries_for_model(seed_run, "openai/gpt-4.1-mini", out_dir)

    output = out_dir / "api_queries.csv"
    raw = output.read_bytes()
    assert count == 1
    assert not raw.startswith(b"\xef\xbb\xbf")
    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "query_id": "q001",
            "query": "Need AI recommendations",
            "target_brand": "AlphaXXXX",
            "persona": "owner",
            "journey_stage": "aware",
            "scenario_provider": "openrouter",
            "scenario_model": "openai/gpt-4.1-mini",
            "api_status": "success",
            "notes": "old",
        }
    ]


def test_seed_queries_for_model_can_limit_seeded_rows(tmp_path: Path):
    seed_run = tmp_path / "seed"
    seed_run.mkdir()
    (seed_run / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,query,target_brand,persona,journey_stage,scenario_provider,scenario_model,api_status,notes",
                "q001,Need AI recommendations,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
                "q002,Need GEO help,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
                "q003,Need AI visibility,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    count = seed_queries_for_model(seed_run, "openai/gpt-4.1-mini", out_dir, limit=2)

    with (out_dir / "api_queries.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert count == 2
    assert [row["query_id"] for row in rows] == ["q001", "q002"]


def test_seed_queries_for_model_retargets_available_seed_rows_when_model_is_missing(tmp_path: Path):
    seed_run = tmp_path / "seed"
    seed_run.mkdir()
    (seed_run / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,query,target_brand,persona,journey_stage,scenario_provider,scenario_model,api_status,notes",
                "q001,Need AI recommendations,AlphaXXXX,owner,aware,openrouter,google/gemini-2.5-flash,success,old",
                "q002,Need GEO help,AlphaXXXX,owner,aware,openrouter,google/gemini-2.5-flash,success,old",
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    count = seed_queries_for_model(seed_run, "google/gemini-3.5-flash", out_dir, limit=1)

    with (out_dir / "api_queries.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert count == 1
    assert rows[0]["query"] == "Need AI recommendations"
    assert rows[0]["scenario_provider"] == "openrouter"
    assert rows[0]["scenario_model"] == "google/gemini-3.5-flash"


def test_seed_queries_cli_can_run_from_script_path(tmp_path: Path):
    seed_run = tmp_path / "seed"
    seed_run.mkdir()
    (seed_run / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,query,target_brand,persona,journey_stage,scenario_provider,scenario_model,api_status,notes",
                "q001,Need AI recommendations,AlphaXXXX,owner,aware,openrouter,openai/gpt-4.1-mini,success,old",
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [
            "python",
            "scripts/seed_api_queries.py",
            "--seed-run-dir",
            str(seed_run),
            "--model",
            "openai/gpt-4.1-mini",
            "--output-dir",
            str(out_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
    assert (out_dir / "api_queries.csv").exists()
