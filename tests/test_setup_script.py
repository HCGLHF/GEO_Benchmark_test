from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_setup_script_bootstraps_team_environment() -> None:
    script = ROOT / "setup.ps1"

    assert script.exists()

    text = script.read_text(encoding="utf-8")
    required_fragments = [
        "py -3.11",
        "-m venv",
        ".venv",
        "python -m pip install -U pip",
        "python -m pip install -e",
        "python -m playwright install chromium",
        ".env.example",
        "verify_cloud_import.py",
        "scripts.ui_app.server",
    ]

    for fragment in required_fragments:
        assert fragment in text


def test_readme_points_new_teammates_to_setup_script() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert ".\\setup.ps1" in readme
