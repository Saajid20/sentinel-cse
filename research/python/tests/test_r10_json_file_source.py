from __future__ import annotations

import json
import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    DirectoryJsonDocumentSource,
    JsonFileDocumentSource,
    ingest_documents,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-json-source-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def make_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "document_id": "doc-001",
        "source_type": "NEWS",
        "title": "CBSL market update",
        "url": "https://example.com/cbsl-market-update",
        "published_at": "2026-05-23T10:00:00Z",
        "retrieved_at": "2026-05-23T10:30:00Z",
        "raw_text": "CBSL said liquidity conditions are improving.",
        "normalized_text": "CBSL said liquidity conditions are improving.",
        "tickers_hint": ["COMB.N0000"],
        "sectors_hint": ["BANKING"],
        "metadata": {"priority": 1},
    }
    payload.update(overrides)
    return payload


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_json_file_document_source_loads_one_valid_json_file(tmp_path: Path) -> None:
    file_path = tmp_path / "document.json"
    write_json(file_path, make_payload())

    source = JsonFileDocumentSource(file_path)
    documents = source.fetch()

    assert len(documents) == 1
    assert isinstance(documents[0], SourceDocument)
    assert documents[0].document_id == "doc-001"


def test_json_file_document_source_raises_file_not_found_for_missing_file(
    tmp_path: Path,
) -> None:
    source = JsonFileDocumentSource(tmp_path / "missing.json")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_json_file_document_source_raises_value_error_for_invalid_json(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "document.json"
    file_path.write_text("{not-json}", encoding="utf-8")
    source = JsonFileDocumentSource(file_path)

    with pytest.raises(ValueError, match="Invalid JSON"):
        source.fetch()


def test_json_file_document_source_raises_value_error_for_schema_invalid_json(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "document.json"
    write_json(file_path, {"document_id": "doc-001"})
    source = JsonFileDocumentSource(file_path)

    with pytest.raises(ValueError, match="Invalid SourceDocument"):
        source.fetch()


def test_directory_json_document_source_loads_multiple_files_in_sorted_order(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "b.json", make_payload(document_id="doc-b"))
    write_json(tmp_path / "a.json", make_payload(document_id="doc-a"))

    source = DirectoryJsonDocumentSource(tmp_path)
    documents = source.fetch()

    assert [document.document_id for document in documents] == ["doc-a", "doc-b"]


def test_directory_json_document_source_returns_empty_list_when_no_files_match(
    tmp_path: Path,
) -> None:
    source = DirectoryJsonDocumentSource(tmp_path)

    assert source.fetch() == []


def test_directory_json_document_source_raises_file_not_found_for_missing_directory(
    tmp_path: Path,
) -> None:
    source = DirectoryJsonDocumentSource(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_directory_json_document_source_raises_value_error_with_file_path_when_invalid(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "bad.json"
    invalid_path.write_text("{not-json}", encoding="utf-8")
    source = DirectoryJsonDocumentSource(tmp_path)

    with pytest.raises(ValueError, match=str(invalid_path).replace("\\", "\\\\")):
        source.fetch()


def test_directory_json_document_source_supports_custom_pattern(tmp_path: Path) -> None:
    write_json(tmp_path / "first.doc.json", make_payload(document_id="doc-first"))
    write_json(tmp_path / "ignored.json", make_payload(document_id="doc-ignored"))

    source = DirectoryJsonDocumentSource(tmp_path, pattern="*.doc.json")
    documents = source.fetch()

    assert [document.document_id for document in documents] == ["doc-first"]


def test_json_file_source_can_be_used_with_ingest_documents_and_local_store(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "document.json"
    write_json(source_path, make_payload())
    source = JsonFileDocumentSource(source_path, name="manual-json")
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    result = ingest_documents(source, store)
    loaded = store.load_all()

    assert result.source_name == "manual-json"
    assert result.fetched_count == 1
    assert result.stored_count == 1
    assert result.document_ids == ["doc-001"]
    assert len(loaded) == 1
