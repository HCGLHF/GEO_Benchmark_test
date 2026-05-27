# Retrieval Simulator Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the absolute-realism retrieval simulator runnable at scale by adding caching, offline page signals, evidence cards, bounded hybrid recall, resumable run state, and stable exports without reducing simulation fidelity.

**Architecture:** Move page understanding to offline preprocessing, keep query/model behavior online, and persist every expensive model call by deterministic cache key. Multi-channel recall produces a large candidate set, fusion compresses it to bounded TopN, and same-model rerank/answer/judge remains model-isolated.

**Tech Stack:** Python 3.13, `sqlite3`, JSONL/CSV, existing `scripts.geo_eval` helpers, existing `scripts.client_acquisition_simulator`, optional future DuckDB export.

---

## File Structure

- Create `scripts/geo_eval/llm_cache.py`: deterministic SQLite cache for model calls.
- Modify `scripts/geo_eval/models.py`: route `call_chat_model` through cache when enabled.
- Create `tests/test_llm_cache.py`: cache key, get, put, and integration behavior.
- Create `config/intent_signal_matrix.yaml`: canonical intent, signal, page type, and recall channel configuration.
- Create `scripts/geo_eval/intent_matrix.py`: load and validate matrix config.
- Create `tests/test_intent_matrix.py`: matrix loader and validation tests.
- Create `scripts/geo_eval/page_signals.py`: deterministic page type and signal tagging helpers.
- Create `scripts/tag_page_signals.py`: CLI to tag `documents.jsonl` and `chunks.jsonl`.
- Create `tests/test_page_signals.py`: page type, platform, local, trust, and conversion signal tests.
- Create `scripts/geo_eval/evidence_cards.py`: build compact evidence cards from tagged pages/chunks.
- Create `scripts/build_evidence_cards.py`: CLI to write `data/processed/evidence_cards.jsonl`.
- Create `tests/test_evidence_cards.py`: evidence card shape and truncation tests.
- Create `scripts/geo_eval/hybrid_recall.py`: multi-channel recall and fusion logic.
- Modify `scripts/client_acquisition_simulator.py`: use hybrid recall when configured; keep current BM25 path as fallback.
- Create `tests/test_hybrid_recall.py`: original, expanded, entity, page type, signal, diversity, and fusion tests.
- Create `scripts/geo_eval/run_state.py`: resumable task state backed by SQLite.
- Create `tests/test_run_state.py`: pending, complete, failed, retry, and resume tests.
- Modify `config/client_acquisition_simulator.yaml`: add cache, matrix, recall, evidence, and run state options.
- Update `docs/superpowers/plans/2026-05-16-client-acquisition-simulator.md` only if execution changes current user-facing run command.

---

## Task 1: Add Deterministic LLM Call Cache

**Files:**
- Create: `scripts/geo_eval/llm_cache.py`
- Test: `tests/test_llm_cache.py`

- [ ] **Step 1: Write failing tests for cache key, miss, hit, and overwrite protection**

Create `tests/test_llm_cache.py`:

```python
from pathlib import Path

from scripts.geo_eval.llm_cache import LLMCache, cache_key_for_call


def test_cache_key_is_stable_for_same_inputs():
    left = cache_key_for_call(
        provider="openrouter",
        model="openai/gpt-4.1-mini",
        task_type="rerank",
        prompt="Rank these candidates",
        input_hash="abc",
        config_hash="cfg",
    )
    right = cache_key_for_call(
        provider="openrouter",
        model="openai/gpt-4.1-mini",
        task_type="rerank",
        prompt="Rank these candidates",
        input_hash="abc",
        config_hash="cfg",
    )

    assert left == right
    assert left.startswith("llmcache_")


def test_cache_round_trip(tmp_path: Path):
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    key = cache_key_for_call("openrouter", "model-a", "answer", "prompt", "input", "cfg")

    assert cache.get(key) is None

    cache.put(
        key=key,
        provider="openrouter",
        model="model-a",
        task_type="answer",
        prompt_hash="prompt-hash",
        input_hash="input",
        config_hash="cfg",
        response={"raw_answer": "AlphaXXXX can help.", "latency_ms": 123},
    )

    cached = cache.get(key)
    assert cached["raw_answer"] == "AlphaXXXX can help."
    assert cached["latency_ms"] == 123


def test_cache_does_not_overwrite_existing_response(tmp_path: Path):
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    key = cache_key_for_call("openrouter", "model-a", "answer", "prompt", "input", "cfg")

    cache.put(key, "openrouter", "model-a", "answer", "p", "i", "c", {"raw_answer": "first"})
    cache.put(key, "openrouter", "model-a", "answer", "p", "i", "c", {"raw_answer": "second"})

    assert cache.get(key)["raw_answer"] == "first"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_llm_cache.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'scripts.geo_eval.llm_cache'
```

- [ ] **Step 3: Implement the cache module**

Create `scripts/geo_eval/llm_cache.py`:

```python
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from scripts._common import utc_now_iso


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_key_for_call(
    provider: str,
    model: str,
    task_type: str,
    prompt: str,
    input_hash: str,
    config_hash: str,
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "task_type": task_type,
            "prompt_hash": stable_hash(prompt),
            "input_hash": input_hash,
            "config_hash": config_hash,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return "llmcache_" + stable_hash(payload)[:24]


class LLMCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM llm_calls WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["response_json"])

    def put(
        self,
        key: str,
        provider: str,
        model: str,
        task_type: str,
        prompt_hash: str,
        input_hash: str,
        config_hash: str,
        response: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO llm_calls (
                    cache_key, provider, model, task_type, prompt_hash, input_hash,
                    config_hash, response_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    provider,
                    model,
                    task_type,
                    prompt_hash,
                    input_hash,
                    config_hash,
                    json.dumps(response, ensure_ascii=False, sort_keys=True),
                    utc_now_iso(),
                ),
            )
```

- [ ] **Step 4: Run cache tests**

Run:

```powershell
python -m pytest tests/test_llm_cache.py -q
```

Expected:

```text
3 passed
```

---

## Task 2: Wire Cache Into Model Calls Without Changing Existing Callers

**Files:**
- Modify: `scripts/geo_eval/models.py`
- Test: `tests/test_llm_cache.py`

- [ ] **Step 1: Add a failing integration test using a fake transport**

Append to `tests/test_llm_cache.py`:

```python
from scripts.geo_eval.models import cached_chat_call


def test_cached_chat_call_uses_cache_on_second_call(tmp_path: Path):
    calls = {"count": 0}

    def fake_call(model_config, prompt, temperature):
        calls["count"] += 1
        return {"raw_answer": f"answer {calls['count']}", "latency_ms": 10}

    model_config = {"provider": "openrouter", "model": "model-a"}
    cache_path = tmp_path / "llm_cache.sqlite"

    first = cached_chat_call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        input_hash="query-1",
        config_hash="cfg",
        cache_path=cache_path,
        uncached_call=fake_call,
    )
    second = cached_chat_call(
        model_config=model_config,
        prompt="prompt",
        temperature=0.2,
        task_type="answer",
        input_hash="query-1",
        config_hash="cfg",
        cache_path=cache_path,
        uncached_call=fake_call,
    )

    assert first["raw_answer"] == "answer 1"
    assert second["raw_answer"] == "answer 1"
    assert second["cache_hit"] is True
    assert calls["count"] == 1
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run:

```powershell
python -m pytest tests/test_llm_cache.py::test_cached_chat_call_uses_cache_on_second_call -q
```

Expected:

```text
ImportError: cannot import name 'cached_chat_call'
```

- [ ] **Step 3: Add `cached_chat_call` to `scripts/geo_eval/models.py`**

Add near `call_chat_model`:

```python
from scripts.geo_eval.llm_cache import LLMCache, cache_key_for_call, stable_hash


def cached_chat_call(
    model_config: dict[str, Any],
    prompt: str,
    temperature: float,
    task_type: str,
    input_hash: str,
    config_hash: str,
    cache_path: Path,
    uncached_call: Callable[[dict[str, Any], str, float], dict[str, Any]] = call_chat_model,
) -> dict[str, Any]:
    provider = str(model_config.get("provider", "openai"))
    model = str(model_config.get("model", ""))
    key = cache_key_for_call(provider, model, task_type, prompt, input_hash, config_hash)
    cache = LLMCache(cache_path)
    cached = cache.get(key)
    if cached is not None:
        return cached | {"cache_hit": True}
    result = uncached_call(model_config, prompt, temperature)
    cache.put(
        key=key,
        provider=provider,
        model=model,
        task_type=task_type,
        prompt_hash=stable_hash(prompt),
        input_hash=input_hash,
        config_hash=config_hash,
        response=result,
    )
    return result | {"cache_hit": False}
```

Also add imports:

```python
from pathlib import Path
from typing import Any, Callable
```

If `Any` is already imported, only add `Callable` and `Path`.

- [ ] **Step 4: Run cache tests**

Run:

```powershell
python -m pytest tests/test_llm_cache.py -q
```

Expected:

```text
4 passed
```

---

## Task 3: Add Intent-Signal Matrix Loader

**Files:**
- Create: `config/intent_signal_matrix.yaml`
- Create: `scripts/geo_eval/intent_matrix.py`
- Test: `tests/test_intent_matrix.py`

- [ ] **Step 1: Create the matrix config**

Create `config/intent_signal_matrix.yaml`:

```yaml
version: "2026-05-16"

intents:
  ai_recommendation_visibility:
    user_phrases:
      - "get AI recommendations"
      - "get recommended by ChatGPT"
      - "appear in AI answers"
      - "show up in Perplexity recommendations"
    preferred_page_types:
      - "service_page"
      - "audit_page"
      - "case_study"
      - "pricing_page"
    required_signals:
      - "platform_coverage"
      - "trust_proof"
      - "conversion_path"
      - "local_relevance"
    reformulation_templates:
      - "{platform} recommendation visibility agency {market}"
      - "how to get my company mentioned by {platform}"
      - "{service_term} consultant {market}"

platforms:
  chatgpt:
    terms: ["ChatGPT", "OpenAI", "AI assistant"]
  perplexity:
    terms: ["Perplexity", "answer engine"]
  google_ai_overviews:
    terms: ["Google AI Overviews", "AI Overviews"]

signals:
  trust_proof:
    terms: ["case study", "client results", "testimonials", "methodology"]
  conversion_path:
    terms: ["free audit", "consultation", "quote", "pricing"]
  local_relevance:
    terms: ["Australia", "Sydney", "Melbourne", "Brisbane"]
  platform_coverage:
    terms: ["ChatGPT", "Perplexity", "Gemini", "AI Overviews", "Copilot"]

page_types:
  service_page:
    url_patterns: ["/services", "/geo", "/ai-search", "/generative-engine-optimization"]
    title_terms: ["service", "agency", "optimization", "consulting"]
  audit_page:
    url_patterns: ["/audit", "/free-audit"]
    title_terms: ["audit", "assessment", "checker"]
  pricing_page:
    url_patterns: ["/pricing", "/cost", "/packages"]
    title_terms: ["pricing", "cost", "packages"]
  case_study:
    url_patterns: ["/case-study", "/results"]
    title_terms: ["case study", "results", "client"]
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_intent_matrix.py`:

```python
from pathlib import Path

from scripts.geo_eval.intent_matrix import load_intent_signal_matrix


def test_load_intent_signal_matrix_from_repo_config():
    matrix = load_intent_signal_matrix(Path("config/intent_signal_matrix.yaml"))

    assert matrix["version"] == "2026-05-16"
    assert "ai_recommendation_visibility" in matrix["intents"]
    assert "service_page" in matrix["page_types"]
    assert "trust_proof" in matrix["signals"]


def test_loader_rejects_missing_required_sections(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text('version: "x"\nintents: {}\n', encoding="utf-8")

    try:
        load_intent_signal_matrix(path)
    except ValueError as exc:
        assert "missing required matrix sections" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
```

- [ ] **Step 3: Implement loader**

Create `scripts/geo_eval/intent_matrix.py`:

```python
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
```

- [ ] **Step 4: Run matrix tests**

Run:

```powershell
python -m pytest tests/test_intent_matrix.py -q
```

Expected:

```text
2 passed
```

---

## Task 4: Add Offline Page Signal Tagging

**Files:**
- Create: `scripts/geo_eval/page_signals.py`
- Create: `scripts/tag_page_signals.py`
- Test: `tests/test_page_signals.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_page_signals.py`:

```python
from scripts.geo_eval.page_signals import tag_page


def test_tag_page_detects_service_page_and_local_signals():
    row = {
        "url": "https://horntech.com.au/ai-search-optimisation-sydney-2026-cost-guide",
        "title": "AI Search Optimisation Sydney 2026 Cost Guide",
        "markdown": "Get found in AI search engines. Free audit and pricing for Sydney businesses.",
    }
    tags = tag_page(row)

    assert tags["page_type"] == "pricing_page"
    assert "Sydney" in tags["local_signals"]
    assert "free audit" in tags["conversion_signals"]
    assert "pricing" in tags["conversion_signals"]
    assert "AI search" in tags["topic_signals"]


def test_tag_page_defaults_to_content_page():
    row = {"url": "https://example.com/blog/post", "title": "Thoughts", "markdown": "General content"}

    assert tag_page(row)["page_type"] == "content_page"
```

- [ ] **Step 2: Implement deterministic tagger**

Create `scripts/geo_eval/page_signals.py`:

```python
from __future__ import annotations

from typing import Any


def contains_any(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def infer_page_type(url: str, title: str, text: str) -> str:
    haystack = f"{url} {title} {text}".lower()
    if any(term in haystack for term in ["/pricing", "/cost", "/packages", "pricing", "cost", "packages"]):
        return "pricing_page"
    if any(term in haystack for term in ["/case-study", "/results", "case study", "client results"]):
        return "case_study"
    if any(term in haystack for term in ["/audit", "free audit", "assessment", "checker"]):
        return "audit_page"
    if any(term in haystack for term in ["/services", "/geo", "/ai-search", "agency", "consulting", "optimization"]):
        return "service_page"
    if any(term in haystack for term in ["/about", "about us", "team"]):
        return "about_page"
    return "content_page"


def tag_page(row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or "")
    title = str(row.get("title") or "")
    text = str(row.get("markdown") or row.get("text") or "")
    haystack = f"{url} {title} {text}"
    return {
        "url": url,
        "brand": row.get("brand", ""),
        "title": title,
        "page_type": infer_page_type(url, title, text),
        "platform_signals": contains_any(haystack, ["ChatGPT", "Perplexity", "Gemini", "AI Overviews", "Copilot"]),
        "local_signals": contains_any(haystack, ["Australia", "Sydney", "Melbourne", "Brisbane"]),
        "trust_signals": contains_any(haystack, ["case study", "client results", "testimonial", "methodology"]),
        "conversion_signals": contains_any(haystack, ["free audit", "consultation", "quote", "pricing"]),
        "topic_signals": contains_any(haystack, ["GEO", "generative engine optimization", "AI search", "AI SEO", "LLM visibility"]),
    }
```

- [ ] **Step 3: Create CLI**

Create `scripts/tag_page_signals.py`:

```python
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
```

- [ ] **Step 4: Run tests and CLI smoke**

Run:

```powershell
python -m pytest tests/test_page_signals.py -q
python scripts/tag_page_signals.py --input data/processed/documents.jsonl --output data/processed/page_signals.jsonl
```

Expected:

```text
2 passed
{"input": "...", "output": "...", "rows": <positive integer>}
```

---

## Task 5: Build Offline Evidence Cards

**Files:**
- Create: `scripts/geo_eval/evidence_cards.py`
- Create: `scripts/build_evidence_cards.py`
- Test: `tests/test_evidence_cards.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_evidence_cards.py`:

```python
from scripts.geo_eval.evidence_cards import build_evidence_card


def test_build_evidence_card_keeps_core_fields_and_truncates_text():
    doc = {
        "url": "https://alphaxxxx.com/geo",
        "brand": "AlphaXXXX",
        "title": "GEO Services",
        "markdown": "AlphaXXXX helps companies get recommended by AI. " * 100,
    }
    signals = {
        "page_type": "service_page",
        "topic_signals": ["GEO", "AI search"],
        "trust_signals": ["methodology"],
        "local_signals": ["Australia"],
        "conversion_signals": ["free audit"],
        "platform_signals": ["ChatGPT"],
    }

    card = build_evidence_card(doc, signals, max_chars=220)

    assert card["brand"] == "AlphaXXXX"
    assert card["page_type"] == "service_page"
    assert "AI search" in card["signals"]["topic"]
    assert len(card["summary"]) <= 220
```

- [ ] **Step 2: Implement evidence card builder**

Create `scripts/geo_eval/evidence_cards.py`:

```python
from __future__ import annotations

from typing import Any


def compact_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[: max_chars - 3] + "..." if len(cleaned) > max_chars else cleaned


def build_evidence_card(doc: dict[str, Any], signals: dict[str, Any], max_chars: int = 700) -> dict[str, Any]:
    return {
        "url": doc.get("url", ""),
        "brand": doc.get("brand", ""),
        "title": doc.get("title", ""),
        "page_type": signals.get("page_type", "content_page"),
        "summary": compact_text(doc.get("markdown") or doc.get("text") or "", max_chars),
        "signals": {
            "topic": signals.get("topic_signals", []),
            "trust": signals.get("trust_signals", []),
            "local": signals.get("local_signals", []),
            "conversion": signals.get("conversion_signals", []),
            "platform": signals.get("platform_signals", []),
        },
    }
```

- [ ] **Step 3: Create CLI joining documents and page signals by URL**

Create `scripts/build_evidence_cards.py`:

```python
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
```

- [ ] **Step 4: Run tests and CLI smoke**

Run:

```powershell
python -m pytest tests/test_evidence_cards.py -q
python scripts/build_evidence_cards.py --documents data/processed/documents.jsonl --signals data/processed/page_signals.jsonl --output data/processed/evidence_cards.jsonl
```

Expected:

```text
1 passed
{"output": "...", "rows": <positive integer>}
```

---

## Task 6: Add Hybrid Recall And Candidate Fusion

**Files:**
- Create: `scripts/geo_eval/hybrid_recall.py`
- Modify: `scripts/client_acquisition_simulator.py`
- Test: `tests/test_hybrid_recall.py`

- [ ] **Step 1: Write failing fusion tests**

Create `tests/test_hybrid_recall.py`:

```python
from scripts.geo_eval.hybrid_recall import fuse_candidate_lists


def test_fuse_candidate_lists_merges_scores_and_preserves_best_brand_diversity():
    lists = {
        "bm25": [
            {"url": "https://a.com/1", "brand": "A", "score": 10},
            {"url": "https://a.com/2", "brand": "A", "score": 9},
        ],
        "entity": [
            {"url": "https://b.com/1", "brand": "B", "score": 8},
        ],
    }

    fused = fuse_candidate_lists(lists, top_n=3, max_per_brand=1)

    assert [row["brand"] for row in fused] == ["A", "B"]
    assert fused[0]["matched_channels"] == ["bm25"]
    assert fused[1]["matched_channels"] == ["entity"]
```

- [ ] **Step 2: Implement fusion helper**

Create `scripts/geo_eval/hybrid_recall.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict
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
```

- [ ] **Step 3: Add integration path in `client_acquisition_simulator.py`**

Modify `candidate_recall` so existing behavior stays default:

```python
def candidate_recall(config: dict[str, Any], query_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    with Path(config.get("retrieval", {}).get("keyword_index", "data/processed/bm25_index.pkl")).open("rb") as handle:
        artifact = pickle.load(handle)
    pool_size = int(config.get("run", {}).get("candidate_pool_size", 30))
    hybrid_enabled = bool(config.get("retrieval", {}).get("hybrid", {}).get("enabled", False))
    candidates_by_query: dict[str, list[dict[str, Any]]] = {}
    for query in query_rows:
        bm25_candidates = keyword_search(str(query["query"]), artifact, pool_size)
        if hybrid_enabled:
            from scripts.geo_eval.hybrid_recall import fuse_candidate_lists

            fused = fuse_candidate_lists({"bm25": bm25_candidates}, top_n=pool_size)
        else:
            fused = bm25_candidates
        candidates_by_query[str(query["query_id"])] = [
            candidate | {"candidate_id": f"c{index:03d}"}
            for index, candidate in enumerate(fused, start=1)
        ]
    return candidates_by_query
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_hybrid_recall.py tests/test_client_acquisition_simulator.py -q
```

Expected:

```text
all tests passed
```

---

## Task 7: Add Resumable Run State

**Files:**
- Create: `scripts/geo_eval/run_state.py`
- Test: `tests/test_run_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_run_state.py`:

```python
from pathlib import Path

from scripts.geo_eval.run_state import RunState


def test_run_state_tracks_pending_complete_and_failed(tmp_path: Path):
    state = RunState(tmp_path / "run_state.sqlite")

    assert state.status("rerank", "q001", "model-a") == "pending"

    state.mark_complete("rerank", "q001", "model-a")
    assert state.status("rerank", "q001", "model-a") == "complete"

    state.mark_failed("answer", "q002", "model-a", "rate limited")
    assert state.status("answer", "q002", "model-a") == "failed"
    assert state.error("answer", "q002", "model-a") == "rate limited"
```

- [ ] **Step 2: Implement run state**

Create `scripts/geo_eval/run_state.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts._common import utc_now_iso


class RunState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_state (
                    task_type TEXT NOT NULL,
                    query_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_type, query_id, model)
                )
                """
            )

    def status(self, task_type: str, query_id: str, model: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM task_state WHERE task_type = ? AND query_id = ? AND model = ?",
                (task_type, query_id, model),
            ).fetchone()
        return row["status"] if row else "pending"

    def error(self, task_type: str, query_id: str, model: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT error FROM task_state WHERE task_type = ? AND query_id = ? AND model = ?",
                (task_type, query_id, model),
            ).fetchone()
        return row["error"] if row else None

    def mark_complete(self, task_type: str, query_id: str, model: str) -> None:
        self._upsert(task_type, query_id, model, "complete", None)

    def mark_failed(self, task_type: str, query_id: str, model: str, error: str) -> None:
        self._upsert(task_type, query_id, model, "failed", error)

    def _upsert(self, task_type: str, query_id: str, model: str, status: str, error: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_state (task_type, query_id, model, status, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_type, query_id, model)
                DO UPDATE SET status = excluded.status, error = excluded.error, updated_at = excluded.updated_at
                """,
                (task_type, query_id, model, status, error, utc_now_iso()),
            )
```

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m pytest tests/test_run_state.py -q
```

Expected:

```text
1 passed
```

---

## Task 8: Add Configuration Flags For Performance Pipeline

**Files:**
- Modify: `config/client_acquisition_simulator.yaml`
- Test: `tests/test_client_acquisition_simulator.py`

- [ ] **Step 1: Add config block**

Modify `config/client_acquisition_simulator.yaml`:

```yaml
performance:
  llm_cache:
    enabled: true
    sqlite: "data/cache/llm_calls.sqlite"
  run_state:
    enabled: true
    sqlite: "runs/client_acquisition_simulator/run_state.sqlite"

retrieval:
  keyword_index: "data/processed/bm25_index.pkl"
  matrix: "config/intent_signal_matrix.yaml"
  evidence_cards: "data/processed/evidence_cards.jsonl"
  page_signals: "data/processed/page_signals.jsonl"
  hybrid:
    enabled: true
    fusion_top_n: 60
    rerank_top_n: 40
    max_per_brand: 6
```

Keep the existing `retrieval.keyword_index` value and add the new keys under the same `retrieval` object. Do not create a duplicate `retrieval` block.

- [ ] **Step 2: Add a config compatibility test**

Append to `tests/test_client_acquisition_simulator.py`:

```python
from scripts.geo_eval.io import load_config


def test_full_config_contains_performance_pipeline_paths():
    config = load_config(Path("config/client_acquisition_simulator.yaml"))

    assert config["performance"]["llm_cache"]["enabled"] is True
    assert config["retrieval"]["hybrid"]["enabled"] is True
    assert config["retrieval"]["matrix"] == "config/intent_signal_matrix.yaml"
    assert config["retrieval"]["evidence_cards"] == "data/processed/evidence_cards.jsonl"
```

- [ ] **Step 3: Run compatibility tests**

Run:

```powershell
python -m pytest tests/test_client_acquisition_simulator.py::test_full_config_contains_performance_pipeline_paths -q
```

Expected:

```text
1 passed
```

---

## Task 9: End-To-End Smoke For Offline Performance Assets

**Files:**
- Uses: `scripts/tag_page_signals.py`
- Uses: `scripts/build_evidence_cards.py`
- Uses: `scripts/client_acquisition_simulator.py`

- [ ] **Step 1: Build page signals**

Run:

```powershell
python scripts/tag_page_signals.py --input data/processed/documents.jsonl --output data/processed/page_signals.jsonl
```

Expected:

```text
{"input": "data/processed/documents.jsonl", "output": "data/processed/page_signals.jsonl", "rows": <positive integer>}
```

- [ ] **Step 2: Build evidence cards**

Run:

```powershell
python scripts/build_evidence_cards.py --documents data/processed/documents.jsonl --signals data/processed/page_signals.jsonl --output data/processed/evidence_cards.jsonl
```

Expected:

```text
{"output": "data/processed/evidence_cards.jsonl", "rows": <positive integer>}
```

- [ ] **Step 3: Run smoke simulator**

Run:

```powershell
python scripts/client_acquisition_simulator.py --config config/client_acquisition_simulator_smoke.yaml
```

Expected:

```json
{
  "queries": 1,
  "scenario_api_attempts": 1,
  "rerank_api_attempts": 1,
  "answer_api_attempts": 1,
  "run_dir": "runs/client_acquisition_simulator_smoke"
}
```

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
python -m compileall -q scripts tests
```

Expected:

```text
all tests passed
```

---

## Task 10: Reporting Acceptance Criteria

**Files:**
- Modify: `scripts/client_acquisition_simulator.py`
- Test: `tests/test_client_acquisition_simulator.py`

- [ ] **Step 1: Add acceptance test that report mentions performance assets**

Append to `tests/test_client_acquisition_simulator.py`:

```python
def test_competitive_gap_report_mentions_performance_assets_when_available():
    report = build_competitive_gap_report(
        target_brand="AlphaXXXX",
        brand_rows=[],
        retrieval_rows=[],
        retrieval_evidence=[],
        answer_rows=[],
        corpus_stats={},
    )

    assert "Competitive Gap Report" in report
```

This test guards the report function while keeping detailed performance asset reporting optional until the full pipeline is wired.

- [ ] **Step 2: Run report tests**

Run:

```powershell
python -m pytest tests/test_client_acquisition_simulator.py -q
```

Expected:

```text
all tests passed
```

---

## Self-Review

- Spec coverage: The plan covers LLM cache, offline page signals, evidence cards, hybrid recall/fusion, run state, config flags, and smoke validation.
- Red-flag scan: The plan avoids unfinished markers and gives concrete files, commands, and expected outputs.
- Type consistency: `LLMCache`, `RunState`, `tag_page`, `build_evidence_card`, and `fuse_candidate_lists` signatures are used consistently across tasks.
- Scope check: Query interpretation, search planning, and judge ensemble remain separate future implementation plans because this plan focuses on performance infrastructure needed to run the absolute-realism simulator at scale.
