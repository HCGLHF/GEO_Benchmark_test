from __future__ import annotations

from collections import Counter
from typing import Any


CHANNEL_WEIGHTS = {
    "bm25": 1.0,
    "expanded_bm25": 0.9,
    "semantic": 1.0,
    "entity": 0.75,
    "page_type": 0.7,
    "signal": 0.7,
    "brand_guardrail": 0.4,
}


def fuse_candidate_lists(
    channel_results: dict[str, list[dict[str, Any]]],
    top_n: int,
    max_per_brand: int = 6,
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for channel, rows in channel_results.items():
        weight = CHANNEL_WEIGHTS.get(channel, 0.5)
        for rank, row in enumerate(rows, start=1):
            url = str(row.get("url") or row.get("candidate_id") or "")
            if not url:
                continue
            existing = by_url.setdefault(url, row | {"fusion_score": 0.0, "matched_channels": []})
            existing["fusion_score"] += weight / rank
            if channel not in existing["matched_channels"]:
                existing["matched_channels"].append(channel)
    sorted_rows = sorted(by_url.values(), key=lambda row: (-float(row["fusion_score"]), str(row.get("url", ""))))
    brand_counts: Counter[str] = Counter()
    fused = []
    for row in sorted_rows:
        brand = str(row.get("brand") or "Unknown")
        if brand_counts[brand] >= max_per_brand:
            continue
        brand_counts[brand] += 1
        fused.append(row)
        if len(fused) >= top_n:
            break
    return fused
