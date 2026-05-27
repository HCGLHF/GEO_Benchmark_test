from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REQUIRED_SECTIONS = {"version", "intents", "platforms", "signals", "page_types"}


def load_intent_signal_matrix(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        matrix = yaml.safe_load(handle) or {}
    missing = REQUIRED_SECTIONS - set(matrix)
    if missing:
        raise ValueError(f"missing required matrix sections: {sorted(missing)}")
    if not matrix["intents"]:
        raise ValueError("intent_signal_matrix must define at least one intent")
    if not matrix["page_types"]:
        raise ValueError("intent_signal_matrix must define at least one page type")
    return matrix
