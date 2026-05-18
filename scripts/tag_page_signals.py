from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_eval.page_signals import tag_page


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag processed documents with page type and GEO signals.")
    parser.add_argument("--input", default="data/processed/documents.jsonl")
    parser.add_argument("--output", default="data/processed/page_signals.jsonl")
    args = parser.parse_args()
    rows = []
    with Path(args.input).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(tag_page(json.loads(line)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"input": args.input, "output": args.output, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
