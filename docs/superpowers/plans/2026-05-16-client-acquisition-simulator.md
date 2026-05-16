# Client Acquisition Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an API-first simulator for the journey where potential clients look for GEO help and may be routed toward AlphaXXXX or competitors.

**Architecture:** Add a new `scripts/client_acquisition_simulator.py` orchestration script that reuses existing OpenRouter chat calls, local BM25 candidate recall, existing retrieval metrics, and brand comparison reporting. API calls are used for scenario/query generation, model-specific reranking, and final direct answers; local retrieval remains a candidate generator and fallback.

**Tech Stack:** Python, pytest, CSV/JSONL outputs, OpenRouter-compatible chat completions through existing `scripts.geo_eval.models.call_chat_model`.

---

### Task 1: Scenario Matrix And API Query Generation

**Files:**
- Create: `scripts/client_acquisition_simulator.py`
- Test: `tests/test_client_acquisition_simulator.py`

- [ ] **Step 1: Write failing tests** for deterministic fallback query generation and API-generated query parsing.
- [ ] **Step 2: Implement** client journey stages, personas, prompt construction, JSON parsing, and fallback query rows.
- [ ] **Step 3: Verify** `python -m pytest tests/test_client_acquisition_simulator.py -q` passes.

### Task 2: API Rerank Retrieval

**Files:**
- Modify: `scripts/client_acquisition_simulator.py`
- Test: `tests/test_client_acquisition_simulator.py`

- [ ] **Step 1: Write failing tests** for rerank response parsing and retrieval metric rows grouped by model.
- [ ] **Step 2: Implement** BM25 candidate recall, rerank prompt construction, JSON rank parsing, fallback rank order, `retrieval_by_model.csv`, and `retrieval_evidence_by_model.jsonl`.
- [ ] **Step 3: Verify** simulator tests and existing retrieval tests pass.

### Task 3: Model Answers And Brand Performance By Model

**Files:**
- Modify: `scripts/client_acquisition_simulator.py`
- Test: `tests/test_client_acquisition_simulator.py`

- [ ] **Step 1: Write failing tests** for model answer rows and by-model brand performance aggregation.
- [ ] **Step 2: Implement** final answer calls per model/query, answer evaluation, and `brand_performance_by_model.csv`.
- [ ] **Step 3: Verify** full test suite passes with `python -m pytest -q`.

### Task 4: Run A Small Smoke Simulation

**Files:**
- Create: `config/client_acquisition_simulator.yaml`

- [ ] **Step 1: Add config** with 4 models, 3 personas, 5 journey stages, 1 query per combination.
- [ ] **Step 2: Run** a small smoke command with one model, one persona, one stage when API key is present.
- [ ] **Step 3: Report** output file paths and counts.
