CREATE TABLE IF NOT EXISTS industries (
  industry_id TEXT PRIMARY KEY,
  display_name TEXT,
  region TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO industries (industry_id, display_name, notes)
VALUES ('geo-agency', 'GEO / AI Visibility Agencies', 'Default industry for the initial imported corpus.')
ON CONFLICT (industry_id) DO NOTHING;

ALTER TABLE corpus_versions ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE artifact_objects ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE url_inventory ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE query_sets ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE benchmark_runs ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE retrieval_results ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE generation_results ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE model_call_attempts ADD COLUMN IF NOT EXISTS industry_id TEXT;
ALTER TABLE llm_call_cache ADD COLUMN IF NOT EXISTS industry_id TEXT;

UPDATE corpus_versions SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE artifact_objects SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE url_inventory SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE documents SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE chunks SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE query_sets SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE queries SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE benchmark_runs SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE retrieval_results SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE generation_results SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE model_call_attempts SET industry_id = 'geo-agency' WHERE industry_id IS NULL;
UPDATE llm_call_cache SET industry_id = 'geo-agency' WHERE industry_id IS NULL;

ALTER TABLE corpus_versions ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE artifact_objects ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE url_inventory ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE documents ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE chunks ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE query_sets ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE queries ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE benchmark_runs ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE retrieval_results ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE generation_results ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE model_call_attempts ALTER COLUMN industry_id SET DEFAULT 'geo-agency';
ALTER TABLE llm_call_cache ALTER COLUMN industry_id SET DEFAULT 'geo-agency';

ALTER TABLE corpus_versions ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE artifact_objects ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE url_inventory ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE documents ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE chunks ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE query_sets ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE queries ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE benchmark_runs ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE retrieval_results ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE generation_results ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE model_call_attempts ALTER COLUMN industry_id SET NOT NULL;
ALTER TABLE llm_call_cache ALTER COLUMN industry_id SET NOT NULL;

ALTER TABLE artifact_objects DROP CONSTRAINT IF EXISTS artifact_objects_corpus_version_fkey;
ALTER TABLE url_inventory DROP CONSTRAINT IF EXISTS url_inventory_corpus_version_fkey;
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_corpus_version_fkey;
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_corpus_version_document_id_fkey;
ALTER TABLE queries DROP CONSTRAINT IF EXISTS queries_query_set_version_fkey;
ALTER TABLE benchmark_runs DROP CONSTRAINT IF EXISTS benchmark_runs_corpus_version_fkey;
ALTER TABLE benchmark_runs DROP CONSTRAINT IF EXISTS benchmark_runs_query_set_version_fkey;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'corpus_versions'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (corpus_version)'
  ) THEN
    ALTER TABLE corpus_versions DROP CONSTRAINT corpus_versions_pkey;
    ALTER TABLE corpus_versions ADD CONSTRAINT corpus_versions_pkey PRIMARY KEY (industry_id, corpus_version);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'corpus_versions'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE corpus_versions ADD CONSTRAINT corpus_versions_pkey PRIMARY KEY (industry_id, corpus_version);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'artifact_objects'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (corpus_version, artifact_type, object_key)'
  ) THEN
    ALTER TABLE artifact_objects DROP CONSTRAINT artifact_objects_pkey;
    ALTER TABLE artifact_objects ADD CONSTRAINT artifact_objects_pkey PRIMARY KEY (industry_id, corpus_version, artifact_type, object_key);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'artifact_objects'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE artifact_objects ADD CONSTRAINT artifact_objects_pkey PRIMARY KEY (industry_id, corpus_version, artifact_type, object_key);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'url_inventory'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (corpus_version, url)'
  ) THEN
    ALTER TABLE url_inventory DROP CONSTRAINT url_inventory_pkey;
    ALTER TABLE url_inventory ADD CONSTRAINT url_inventory_pkey PRIMARY KEY (industry_id, corpus_version, url);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'url_inventory'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE url_inventory ADD CONSTRAINT url_inventory_pkey PRIMARY KEY (industry_id, corpus_version, url);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'documents'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (corpus_version, document_id)'
  ) THEN
    ALTER TABLE documents DROP CONSTRAINT documents_pkey;
    ALTER TABLE documents ADD CONSTRAINT documents_pkey PRIMARY KEY (industry_id, corpus_version, document_id);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'documents'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE documents ADD CONSTRAINT documents_pkey PRIMARY KEY (industry_id, corpus_version, document_id);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'chunks'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (corpus_version, chunk_id)'
  ) THEN
    ALTER TABLE chunks DROP CONSTRAINT chunks_pkey;
    ALTER TABLE chunks ADD CONSTRAINT chunks_pkey PRIMARY KEY (industry_id, corpus_version, chunk_id);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'chunks'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE chunks ADD CONSTRAINT chunks_pkey PRIMARY KEY (industry_id, corpus_version, chunk_id);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'query_sets'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (query_set_version)'
  ) THEN
    ALTER TABLE query_sets DROP CONSTRAINT query_sets_pkey;
    ALTER TABLE query_sets ADD CONSTRAINT query_sets_pkey PRIMARY KEY (industry_id, query_set_version);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'query_sets'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE query_sets ADD CONSTRAINT query_sets_pkey PRIMARY KEY (industry_id, query_set_version);
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'queries'::regclass
      AND contype = 'p'
      AND pg_get_constraintdef(oid) = 'PRIMARY KEY (query_set_version, query_id)'
  ) THEN
    ALTER TABLE queries DROP CONSTRAINT queries_pkey;
    ALTER TABLE queries ADD CONSTRAINT queries_pkey PRIMARY KEY (industry_id, query_set_version, query_id);
  ELSIF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'queries'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE queries ADD CONSTRAINT queries_pkey PRIMARY KEY (industry_id, query_set_version, query_id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'corpus_versions_industry_id_fkey'
  ) THEN
    ALTER TABLE corpus_versions
      ADD CONSTRAINT corpus_versions_industry_id_fkey
      FOREIGN KEY (industry_id) REFERENCES industries(industry_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'query_sets_industry_id_fkey'
  ) THEN
    ALTER TABLE query_sets
      ADD CONSTRAINT query_sets_industry_id_fkey
      FOREIGN KEY (industry_id) REFERENCES industries(industry_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'artifact_objects_industry_corpus_fkey'
  ) THEN
    ALTER TABLE artifact_objects
      ADD CONSTRAINT artifact_objects_industry_corpus_fkey
      FOREIGN KEY (industry_id, corpus_version)
      REFERENCES corpus_versions(industry_id, corpus_version) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'url_inventory_industry_corpus_fkey'
  ) THEN
    ALTER TABLE url_inventory
      ADD CONSTRAINT url_inventory_industry_corpus_fkey
      FOREIGN KEY (industry_id, corpus_version)
      REFERENCES corpus_versions(industry_id, corpus_version) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'documents_industry_corpus_fkey'
  ) THEN
    ALTER TABLE documents
      ADD CONSTRAINT documents_industry_corpus_fkey
      FOREIGN KEY (industry_id, corpus_version)
      REFERENCES corpus_versions(industry_id, corpus_version) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chunks_industry_document_fkey'
  ) THEN
    ALTER TABLE chunks
      ADD CONSTRAINT chunks_industry_document_fkey
      FOREIGN KEY (industry_id, corpus_version, document_id)
      REFERENCES documents(industry_id, corpus_version, document_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'queries_industry_query_set_fkey'
  ) THEN
    ALTER TABLE queries
      ADD CONSTRAINT queries_industry_query_set_fkey
      FOREIGN KEY (industry_id, query_set_version)
      REFERENCES query_sets(industry_id, query_set_version) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'benchmark_runs_industry_corpus_fkey'
  ) THEN
    ALTER TABLE benchmark_runs
      ADD CONSTRAINT benchmark_runs_industry_corpus_fkey
      FOREIGN KEY (industry_id, corpus_version)
      REFERENCES corpus_versions(industry_id, corpus_version);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'benchmark_runs_industry_query_set_fkey'
  ) THEN
    ALTER TABLE benchmark_runs
      ADD CONSTRAINT benchmark_runs_industry_query_set_fkey
      FOREIGN KEY (industry_id, query_set_version)
      REFERENCES query_sets(industry_id, query_set_version);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_documents_industry_corpus_brand
  ON documents (industry_id, corpus_version, brand);

CREATE INDEX IF NOT EXISTS idx_documents_industry_corpus_url
  ON documents (industry_id, corpus_version, url);

CREATE INDEX IF NOT EXISTS idx_chunks_industry_corpus_document
  ON chunks (industry_id, corpus_version, document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_industry_corpus_brand
  ON chunks (industry_id, corpus_version, brand);

CREATE INDEX IF NOT EXISTS idx_artifact_objects_industry_corpus
  ON artifact_objects (industry_id, corpus_version, artifact_type);
