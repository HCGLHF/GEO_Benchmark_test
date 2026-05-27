from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CompetitorOption:
    brand: str
    seed_urls: list[str]


@dataclass(frozen=True)
class ModelOption:
    provider: str
    model: str
    note: str | None = None


@dataclass(frozen=True)
class ProjectOptions:
    target_brand: str
    target_domain: str
    default_own_site_url: str
    competitors: list[CompetitorOption]
    models: list[ModelOption]
    sources_path: Path | None
    simulator_config_path: Path | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources_path"] = str(self.sources_path) if self.sources_path else None
        payload["simulator_config_path"] = str(self.simulator_config_path) if self.simulator_config_path else None
        return payload


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _default_url_from_domain(domain: str) -> str:
    domain = domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not domain:
        return "https://alphaxxxx.com/"
    return f"https://{domain}/"


def load_project_options(project_root: Path | str = Path(".")) -> ProjectOptions:
    root = Path(project_root)
    sources_path = root / "config" / "sources.yaml"
    simulator_path = root / "config" / "client_acquisition_simulator.yaml"
    sources = _load_yaml(sources_path)
    simulator = _load_yaml(simulator_path)

    campaign = simulator.get("campaign", {}) if isinstance(simulator.get("campaign"), dict) else {}
    own_site = sources.get("own_site", {}) if isinstance(sources.get("own_site"), dict) else {}
    target_brand = str(campaign.get("target_brand") or own_site.get("brand") or "AlphaXXXX")
    target_domain = str(campaign.get("target_domain") or "alphaxxxx.com")
    seed_urls = own_site.get("seed_urls") if isinstance(own_site.get("seed_urls"), list) else []
    default_own_site_url = str(seed_urls[0]) if seed_urls else _default_url_from_domain(target_domain)

    competitors: list[CompetitorOption] = []
    source_competitors = sources.get("competitors") if isinstance(sources.get("competitors"), list) else []
    for item in source_competitors:
        if not isinstance(item, dict):
            continue
        brand = str(item.get("brand") or "").strip()
        if not brand:
            continue
        item_seed_urls = item.get("seed_urls") if isinstance(item.get("seed_urls"), list) else []
        competitors.append(CompetitorOption(brand=brand, seed_urls=[str(url) for url in item_seed_urls]))

    if not competitors:
        campaign_competitors = campaign.get("competitors") if isinstance(campaign.get("competitors"), list) else []
        competitors = [CompetitorOption(brand=str(brand), seed_urls=[]) for brand in campaign_competitors if str(brand).strip()]

    models: list[ModelOption] = []
    for item in simulator.get("models", []) or []:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip()
        if model:
            models.append(ModelOption(provider=str(item.get("provider") or ""), model=model, note=item.get("note")))

    return ProjectOptions(
        target_brand=target_brand,
        target_domain=target_domain,
        default_own_site_url=default_own_site_url,
        competitors=competitors,
        models=models,
        sources_path=sources_path if sources_path.exists() else None,
        simulator_config_path=simulator_path if simulator_path.exists() else None,
    )
