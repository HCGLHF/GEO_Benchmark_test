from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


RECOMMENDATION_TERMS = re.compile(r"recommend|best|choose|consider|建议|推荐|优先", re.I)


def brand_mentioned(answer: str, brand: str) -> bool:
    return bool(brand and brand.lower() in answer.lower())


def extract_urls(answer: str) -> list[str]:
    return re.findall(r"https?://[^\s\]\)>,]+", answer)


def cited_owned_url(answer: str, owned_urls: list[str]) -> bool:
    answer_urls = extract_urls(answer)
    return any(url.startswith(owned) or owned.startswith(url) for url in answer_urls for owned in owned_urls)


def recommended_brand(answer: str, brand: str) -> bool:
    if not brand_mentioned(answer, brand):
        return False
    lower = answer.lower()
    index = lower.find(brand.lower())
    window = lower[max(0, index - 80) : index + len(brand) + 80]
    return bool(RECOMMENDATION_TERMS.search(window))


def coverage_score(answer: str, query: str) -> int:
    if not answer.strip():
        return 0
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query) if len(term) > 2]
    if not terms:
        return 2
    hits = sum(1 for term in set(terms) if term in answer.lower())
    ratio = hits / max(len(set(terms)), 1)
    if ratio >= 0.75 and len(answer) > 400:
        return 3
    if ratio >= 0.4:
        return 2
    return 1


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def default_retrieval_evidence_path(retrieval_results_path: Path) -> Path:
    return retrieval_results_path.with_name("retrieval_evidence.jsonl")


def load_retrieval_evidence(retrieval_results_path: Path) -> dict[str, list[dict[str, object]]]:
    evidence_path = default_retrieval_evidence_path(retrieval_results_path)
    evidence: dict[str, list[dict[str, object]]] = {}
    if evidence_path.exists():
        with evidence_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                evidence[row["query_id"]] = json.loads(row.get("retrieved_chunks_json") or "[]")
        return evidence

    for row in load_csv(retrieval_results_path):
        evidence[row["query_id"]] = json.loads(row.get("retrieved_chunks_json") or "[]")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate model answers for GEO metrics.")
    parser.add_argument("--queries", default="data/eval/queries.csv")
    parser.add_argument("--retrieval-results", default="data/eval/retrieval_results.csv")
    parser.add_argument("--output", default="data/eval/generation_results.csv")
    parser.add_argument("--mode", choices=["direct", "grounded"], default="grounded")
    args = parser.parse_args()

    api_key = os.getenv("GEO_LLM_API_KEY")
    if not api_key:
        raise SystemExit("Missing GEO_LLM_API_KEY; generation evaluation was not run.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(f"Missing OpenAI-compatible client dependency: {exc}") from exc

    provider = os.getenv("GEO_LLM_PROVIDER", "openai")
    model_name = os.getenv("GEO_LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("GEO_LLM_BASE_URL") or None
    client = OpenAI(api_key=api_key, base_url=base_url)

    queries = load_csv(Path(args.queries))
    retrieval_evidence = load_retrieval_evidence(Path(args.retrieval_results))
    rows: list[dict[str, object]] = []

    for query in queries:
        context = ""
        owned_urls: list[str] = []
        if args.mode == "grounded" and query["query_id"] in retrieval_evidence:
            chunks = retrieval_evidence[query["query_id"]]
            context = "\n\n".join(
                f"URL: {chunk.get('url')}\nBrand: {chunk.get('brand')}\nText: {chunk.get('text', '')}"
                for chunk in chunks
            )
            owned_urls = [
                chunk.get("url", "")
                for chunk in chunks
                if chunk.get("brand") == query.get("target_brand")
            ]

        prompt = (
            "Answer only from the supplied context. Cite URLs from the context. "
            "If context is insufficient, say so. Avoid unsupported claims.\n\n"
            f"Question: {query['query']}\n\nContext:\n{context}"
            if args.mode == "grounded"
            else query["query"]
        )
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        answer = response.choices[0].message.content or ""
        brand = query.get("target_brand", "")
        rows.append(
            {
                "run_id": "generation_run",
                "query_id": query["query_id"],
                "provider": provider,
                "model_name": model_name,
                "mode": args.mode,
                "repeat_index": 0,
                "temperature": 0,
                "prompt_version": "v1",
                "context_top_k": 10,
                "raw_answer": answer,
                "brand_mentioned": brand_mentioned(answer, brand),
                "cited_own_url": cited_owned_url(answer, owned_urls),
                "recommended_own_brand": recommended_brand(answer, brand),
                "competitors_mentioned_json": "[]",
                "citations_json": json.dumps(extract_urls(answer)),
                "answer_coverage_score": coverage_score(answer, query["query"]),
                "unsupported_claims_json": "[]",
                "latency_ms": "",
                "cost_estimate": "",
            }
        )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.output).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote generation results for {len(rows)} queries to {args.output}")


if __name__ == "__main__":
    main()
