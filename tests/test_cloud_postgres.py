from scripts.cloud.postgres import _execute_many, fetch_artifact_rows, fetch_corpus_counts


class FakeCursor:
    def __init__(self):
        self.executed_many = []
        self.executed_one = []

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


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

    counts = fetch_corpus_counts("postgresql://example", "2026-05-22-initial")

    assert counts == {
        "corpus_inventory_count": 1683,
        "corpus_document_count": 1683,
        "corpus_chunk_count": 6225,
        "inventory_rows": 1683,
        "documents": 1683,
        "chunks": 6225,
        "artifacts": 3,
    }
    assert all(params == ("2026-05-22-initial",) for _, params in cursor.executed)


def test_fetch_artifact_rows_returns_named_rows(monkeypatch):
    cursor = FakeReadCursor(
        all_rows=[
            (
                "processed_documents",
                "geo-bucket",
                "processed/2026-05-22-initial/documents.jsonl",
                "abc123",
                19485927,
                "data/processed/documents.jsonl",
                "2026-05-22T00:00:00Z",
            )
        ]
    )
    monkeypatch.setattr("scripts.cloud.postgres._connect", lambda database_url: FakeReadConnection(cursor))

    rows = fetch_artifact_rows("postgresql://example", "2026-05-22-initial")

    assert rows == [
        {
            "artifact_type": "processed_documents",
            "bucket": "geo-bucket",
            "object_key": "processed/2026-05-22-initial/documents.jsonl",
            "sha256": "abc123",
            "size_bytes": 19485927,
            "source_path": "data/processed/documents.jsonl",
            "created_at": "2026-05-22T00:00:00Z",
        }
    ]
