-- Apply sql/002_industry_isolation.sql after this base schema for cloud databases.

-- Apply sql/002_industry_isolation.sql after this base schema for new cloud databases.

CREATE TABLE IF NOT EXISTS corpus_versions (
  corpus_version TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  inventory_count INTEGER NOT NULL DEFAULT 0,
  document_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS artifact_objects (
  corpus_version TEXT NOT NULL REFERENCES corpus_versions(corpus_version) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  bucket TEXT,
  object_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  source_path TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (corpus_version, artifact_type, object_key)
);

CREATE TABLE IF NOT EXISTS url_inventory (
  corpus_version TEXT NOT NULL REFERENCES corpus_versions(corpus_version) ON DELETE CASCADE,
  url TEXT NOT NULL,
  brand TEXT,
  source_type TEXT,
  source_group TEXT,
  seed_url TEXT,
  discovery_method TEXT,
  depth INTEGER,
  status TEXT,
  PRIMARY KEY (corpus_version, url)
);

CREATE TABLE IF NOT EXISTS documents (
  corpus_version TEXT NOT NULL REFERENCES corpus_versions(corpus_version) ON DELETE CASCADE,
  document_id TEXT NOT NULL,
  url TEXT NOT NULL,
  site TEXT,
  brand TEXT,
  title TEXT,
  description TEXT,
  content TEXT NOT NULL,
  source_type TEXT,
  page_type TEXT,
  collected_at TEXT,
  content_hash TEXT,
  PRIMARY KEY (corpus_version, document_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_corpus_brand
  ON documents (corpus_version, brand);

CREATE INDEX IF NOT EXISTS idx_documents_corpus_url
  ON documents (corpus_version, url);

CREATE TABLE IF NOT EXISTS chunks (
  corpus_version TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  url TEXT,
  brand TEXT,
  title TEXT,
  heading TEXT,
  text TEXT NOT NULL,
  source_type TEXT,
  page_type TEXT,
  token_count INTEGER,
  content_hash TEXT,
  PRIMARY KEY (corpus_version, chunk_id),
  FOREIGN KEY (corpus_version, document_id)
    REFERENCES documents(corpus_version, document_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_corpus_document
  ON chunks (corpus_version, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_corpus_brand
  ON chunks (corpus_version, brand);

CREATE TABLE IF NOT EXISTS query_sets (
  query_set_version TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_run_dir TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS queries (
  query_set_version TEXT NOT NULL REFERENCES query_sets(query_set_version) ON DELETE CASCADE,
  query_id TEXT NOT NULL,
  query TEXT NOT NULL,
  intent TEXT,
  priority TEXT,
  target_brand TEXT,
  expected_owned_urls TEXT,
  notes TEXT,
  PRIMARY KEY (query_set_version, query_id)
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
  run_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  corpus_version TEXT REFERENCES corpus_versions(corpus_version),
  query_set_version TEXT REFERENCES query_sets(query_set_version),
  run_mode TEXT,
  provider TEXT,
  model_name TEXT,
  output_s3_key TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS retrieval_results (
  run_id TEXT NOT NULL REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
  query_id TEXT NOT NULL,
  top_k INTEGER,
  own_brand_rank INTEGER,
  own_brand_in_top_3 BOOLEAN,
  own_brand_in_top_5 BOOLEAN,
  own_brand_in_top_10 BOOLEAN,
  winning_brand TEXT,
  winning_source_type TEXT,
  competitor_above_owned BOOLEAN,
  matched_urls_json JSONB,
  retrieved_chunks_json JSONB,
  PRIMARY KEY (run_id, query_id)
);

CREATE TABLE IF NOT EXISTS generation_results (
  run_id TEXT NOT NULL REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
  query_id TEXT NOT NULL,
  provider TEXT,
  model_name TEXT,
  mode TEXT,
  repeat_index INTEGER,
  temperature DOUBLE PRECISION,
  prompt_version TEXT,
  context_top_k INTEGER,
  raw_answer TEXT,
  brand_mentioned BOOLEAN,
  cited_own_url BOOLEAN,
  recommended_own_brand BOOLEAN,
  competitors_mentioned_json JSONB,
  citations_json JSONB,
  answer_coverage_score INTEGER,
  unsupported_claims_json JSONB,
  latency_ms INTEGER,
  cost_estimate DOUBLE PRECISION,
  PRIMARY KEY (run_id, query_id, provider, model_name, mode, repeat_index)
);

CREATE TABLE IF NOT EXISTS model_call_attempts (
  run_id TEXT,
  task_type TEXT NOT NULL,
  query_id TEXT,
  provider TEXT,
  model_name TEXT,
  task_fingerprint TEXT,
  status TEXT,
  error_message TEXT,
  cache_hit BOOLEAN,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_call_cache (
  cache_key TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  task_type TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  response_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
