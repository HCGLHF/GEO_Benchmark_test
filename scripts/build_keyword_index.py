from __future__ import annotations

import argparse
import pickle
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import read_jsonl


CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    chars = CHINESE_RE.findall(text)
    return words + chars


def build_keyword_artifact(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    tokenized = [tokenize(chunk.get("text", "")) for chunk in chunks]
    return {"chunks": chunks, "tokenized": tokenized}


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(artifact, handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a keyword retrieval index.")
    parser.add_argument("--input", default="data/processed/chunks.jsonl")
    parser.add_argument("--output", default="data/processed/bm25_index.pkl")
    args = parser.parse_args()

    chunks = read_jsonl(Path(args.input))
    artifact = build_keyword_artifact(chunks)
    save_artifact(Path(args.output), artifact)
    print(f"Wrote keyword index for {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
