from pathlib import Path

from scripts.ui_app.config_summary import load_project_options


def test_load_project_options_reads_site_competitors_and_models(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        """
own_site:
  brand: AlphaXXXX
  seed_urls:
    - https://alphaxxxx.com/
competitors:
  - brand: HornTech
    seed_urls:
      - https://horntech.com.au/
  - brand: GEO Digital
    seed_urls:
      - https://geodigital.com.au/
""",
        encoding="utf-8",
    )
    (config_dir / "client_acquisition_simulator.yaml").write_text(
        """
campaign:
  target_brand: AlphaXXXX
  competitors:
    - HornTech
    - GEO Digital
models:
  - provider: openrouter
    model: openai/gpt-4.1-mini
  - provider: openrouter
    model: google/gemini-2.5-flash
""",
        encoding="utf-8",
    )

    options = load_project_options(tmp_path)

    assert options.target_brand == "AlphaXXXX"
    assert options.default_own_site_url == "https://alphaxxxx.com/"
    assert [competitor.brand for competitor in options.competitors] == ["HornTech", "GEO Digital"]
    assert [model.model for model in options.models] == ["openai/gpt-4.1-mini", "google/gemini-2.5-flash"]


def test_load_project_options_falls_back_to_campaign_competitors(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "client_acquisition_simulator.yaml").write_text(
        """
campaign:
  target_brand: AlphaXXXX
  target_domain: alphaxxxx.com
  competitors:
    - OtterlyAI
models: []
""",
        encoding="utf-8",
    )

    options = load_project_options(tmp_path)

    assert options.default_own_site_url == "https://alphaxxxx.com/"
    assert [competitor.brand for competitor in options.competitors] == ["OtterlyAI"]
