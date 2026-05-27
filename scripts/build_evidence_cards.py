from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_eval.evidence_cards import build_evidence_card


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compact evidence cards for retrieval rerank.")
    parser.add_argument("--documents", default="data/processed/documents.jsonl")
    parser.add_argument("--signals", default="data/processed/page_signals.jsonl")
    parser.add_argument("--output", default="data/processed/evidence_cards.jsonl")
    args = parser.parse_args()
    docs = read_jsonl(Path(args.documents))
    signal_by_url = {row.get("url"): row for row in read_jsonl(Path(args.signals))}
    cards = [build_evidence_card(doc, signal_by_url.get(doc.get("url"), {})) for doc in docs]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for card in cards:
            handle.write(json.dumps(card, ensure_ascii=False) + "\n")
    print(json.dumps({"output": args.output, "rows": len(cards)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
