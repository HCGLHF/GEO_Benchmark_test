import zipfile
from pathlib import Path

from scripts.cloud.qdrant_snapshot import create_qdrant_zip, qdrant_artifact_key


def test_qdrant_artifact_key_uses_vector_index_prefix():
    assert qdrant_artifact_key("2026-05-22-initial") == "vector-index/2026-05-22-initial/qdrant.zip"


def test_create_qdrant_zip_includes_nested_files(tmp_path: Path):
    source = tmp_path / "vector_db" / "qdrant"
    nested = source / "collections" / "geo"
    nested.mkdir(parents=True)
    (nested / "data.bin").write_bytes(b"abc")
    output = tmp_path / "out" / "qdrant.zip"

    create_qdrant_zip(source, output)

    with zipfile.ZipFile(output, "r") as archive:
        assert archive.namelist() == ["collections/geo/data.bin"]
        assert archive.read("collections/geo/data.bin") == b"abc"
