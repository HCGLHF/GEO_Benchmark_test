from pathlib import Path


def test_industry_isolation_migration_declares_industry_table_and_columns():
    sql = Path("sql/002_industry_isolation.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS industries" in sql
    assert "ALTER TABLE corpus_versions ADD COLUMN IF NOT EXISTS industry_id" in sql
    assert "ALTER TABLE documents ADD COLUMN IF NOT EXISTS industry_id" in sql
    assert "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS industry_id" in sql
    assert "ALTER TABLE artifact_objects ADD COLUMN IF NOT EXISTS industry_id" in sql
    assert "FOREIGN KEY (industry_id, corpus_version)" in sql


def test_initial_schema_points_to_industry_migration_for_new_cloud_databases():
    sql = Path("sql/001_initial_schema.sql").read_text(encoding="utf-8")

    assert "Apply sql/002_industry_isolation.sql after this base schema" in sql
