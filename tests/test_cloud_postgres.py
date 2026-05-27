from scripts.cloud.postgres import (
    _execute_many,
    fetch_artifact_rows,
    fetch_corpus_counts,
    register_artifact_objects,
    upsert_industry,
)


class FakeCursor:
    def __init__(self):
        self.executed_many = []
        self.executed_one = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def executemany(self, sql, rows):
        self.executed_many.append((sql, rows))

    def execute(self, sql, row):
        self.executed_one.append((sql, row))


def test_execute_many_batches_rows_in_one_driver_call():
    cursor = FakeCursor()

    _execute_many(cursor, "insert into sample values (%s)", [(1,), (2,)])

    assert cursor.executed_many == [("insert into sample values (%s)", [(1,), (2,)])]
    assert cursor.executed_one == []


class FakeReadCursor:
    def __init__(self, *, one_rows=None, all_rows=None):
        self.executed = []
        self.one_rows = list(one_rows or [])
        self.all_rows = list(all_rows or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, row):
        self.executed.append((sql, row))

    def fetchone(self):
        return self.one_rows.pop(0)

    def fetchall(self):
        return self.all_rows


class FakeReadConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def test_fetch_corpus_counts_reads_version_and_table_counts(monkeypatch):
    cursor = FakeReadCursor(
        one_rows=[
            (1683, 1683, 6225),
            (1683,),
            (1683,),
            (6225,),
            (3,),
        ]
    )
    monkeypatch.setattr("scripts.cloud.postgres._connect", lambda database_url: FakeReadConnection(cursor))

    counts = fetch_corpus_counts("postgresql://example", "geo-agency", "2026-05-22-initial")

    assert counts == {
        "corpus_inventory_count": 1683,
        "corpus_document_count": 1683,
        "corpus_chunk_count": 6225,
        "inventory_rows": 1683,
        "documents": 1683,
        "chunks": 6225,
        "artifacts": 3,
    }
    assert all(params == ("geo-agency", "2026-05-22-initial") for _, params in cursor.executed)


def test_fetch_artifact_rows_returns_named_rows(monkeypatch):
    cursor = FakeReadCursor(
        all_rows=[
            (
                "processed_documents",
                "geo-agency",
                "geo-bucket",
                "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl",
                "abc123",
                19485927,
                "data/processed/documents.jsonl",
                "2026-05-22T00:00:00Z",
            )
        ]
    )
    monkeypatch.setattr("scripts.cloud.postgres._connect", lambda database_url: FakeReadConnection(cursor))

    rows = fetch_artifact_rows("postgresql://example", "geo-agency", "2026-05-22-initial")

    assert rows == [
        {
            "artifact_type": "processed_documents",
            "industry_id": "geo-agency",
            "bucket": "geo-bucket",
            "object_key": "industries/geo-agency/processed/2026-05-22-initial/documents.jsonl",
            "sha256": "abc123",
            "size_bytes": 19485927,
            "source_path": "data/processed/documents.jsonl",
            "created_at": "2026-05-22T00:00:00Z",
        }
    ]


def test_register_artifact_objects_upserts_artifacts(monkeypatch):
    cursor = FakeCursor()
    connection = FakeReadConnection(cursor)
    monkeypatch.setattr("scripts.cloud.postgres._connect", lambda database_url: connection)

    register_artifact_objects(
        "postgresql://example",
        [
            {
                "industry_id": "geo-agency",
                "corpus_version": "2026-05-22-initial",
                "artifact_type": "qdrant_snapshot",
                "bucket": "geo-bucket",
                "object_key": "industries/geo-agency/vector-index/2026-05-22-initial/qdrant.zip",
                "sha256": "abc123",
                "size_bytes": 42,
                "source_path": "output/cloud/2026-05-22-initial/qdrant.zip",
                "created_at": "2026-05-22T00:00:00Z",
            }
        ],
    )

    assert len(cursor.executed_many) == 2
    industry_sql, industry_rows = cursor.executed_many[0]
    assert "INSERT INTO industries" in industry_sql
    assert industry_rows == [("geo-agency",)]
    sql, rows = cursor.executed_many[1]
    assert "INSERT INTO artifact_objects" in sql
    assert rows == [
        (
            "geo-agency",
            "2026-05-22-initial",
            "qdrant_snapshot",
            "geo-bucket",
            "industries/geo-agency/vector-index/2026-05-22-initial/qdrant.zip",
            "abc123",
            42,
            "output/cloud/2026-05-22-initial/qdrant.zip",
            "2026-05-22T00:00:00Z",
        )
    ]
    assert connection.committed is True


def test_upsert_industry_writes_metadata_and_commits(monkeypatch):
    cursor = FakeCursor()
    connection = FakeReadConnection(cursor)
    monkeypatch.setattr("scripts.cloud.postgres._connect", lambda database_url: connection)

    upsert_industry(
        "postgresql://example",
        industry_id=" Dental ",
        display_name="Dental Clinics",
        region="AU",
        notes="Dental vertical corpus.",
    )

    assert len(cursor.executed_one) == 1
    sql, params = cursor.executed_one[0]
    assert "INSERT INTO industries" in sql
    assert "ON CONFLICT (industry_id) DO UPDATE SET" in sql
    assert params == (
        "dental",
        "Dental Clinics",
        "AU",
        "Dental vertical corpus.",
    )
    assert connection.committed is True
