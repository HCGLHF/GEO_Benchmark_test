from __future__ import annotations

import re


INDUSTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


def normalize_industry_id(value: str) -> str:
    industry_id = value.strip().lower()
    if not INDUSTRY_ID_PATTERN.fullmatch(industry_id):
        raise ValueError(
            "Industry id must be 3-64 lowercase letters, numbers, or hyphens, "
            "and must start and end with a letter or number."
        )
    return industry_id
