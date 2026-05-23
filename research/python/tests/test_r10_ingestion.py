from __future__ import annotations

import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    DocumentSource,
    IngestionResult,
    StaticDocumentSource,
    ingest_documents,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-ingestion-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def make_document(**overrides: object) -> SourceDocument:
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
    return SourceDocument.model_validate(payload)


class ExplodingSource(DocumentSource):
    def fetch(self) -> list[SourceDocument]:
        raise RuntimeError("boom")


class NonListSource(DocumentSource):
    def fetch(self):  # type: ignore[override]
        return "not-a-list"


class InvalidItemSource(DocumentSource):
    def fetch(self):  # type: ignore[override]
        return [make_document(), "bad-item"]


def test_static_document_source_fetch_returns_source_documents() -> None:
    source = StaticDocumentSource([make_document()])

    documents = source.fetch()

    assert len(documents) == 1
    assert isinstance(documents[0], SourceDocument)


def test_static_document_source_fetch_returns_shallow_copy() -> None:
    source = StaticDocumentSource([make_document()])

    fetched_documents = source.fetch()
    fetched_documents.append(make_document(document_id="doc-002"))

    assert len(fetched_documents) == 2
    assert len(source.fetch()) == 1


def test_ingest_documents_stores_fetched_documents(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    documents = [make_document(), make_document(document_id="doc-002")]
    source = StaticDocumentSource(documents)

    ingest_documents(source, store)
    loaded = store.load_all()

    assert loaded == documents


def test_ingest_documents_returns_correct_counts_and_document_ids(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    documents = [make_document(), make_document(document_id="doc-002")]
    source = StaticDocumentSource(documents, name="fixture-source")

    result = ingest_documents(source, store)

    assert result.source_name == "fixture-source"
    assert result.fetched_count == 2
    assert result.stored_count == 2
    assert result.document_ids == ["doc-001", "doc-002"]


def test_ingest_documents_handles_empty_fetch_result(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    source = StaticDocumentSource([])

    result = ingest_documents(source, store)

    assert result.fetched_count == 0
    assert result.stored_count == 0
    assert result.skipped_count == 0
    assert store.load_all() == []


def test_ingest_documents_catches_source_fetch_exception_without_raising(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    result = ingest_documents(ExplodingSource(), store, source_name="exploder")

    assert result.source_name == "exploder"
    assert result.errors == ["boom"]
    assert store.load_all() == []


def test_ingest_documents_rejects_non_list_fetch_result(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    result = ingest_documents(NonListSource(), store)

    assert result.stored_count == 0
    assert result.errors == ["source.fetch() must return a list of SourceDocument objects"]
    assert store.load_all() == []


def test_ingest_documents_rejects_list_with_non_source_document_and_stores_nothing(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    result = ingest_documents(InvalidItemSource(), store, source_name="invalid-items")

    assert result.source_name == "invalid-items"
    assert result.fetched_count == 2
    assert result.stored_count == 0
    assert "non-SourceDocument items" in result.errors[0]
    assert store.load_all() == []


def test_ingest_documents_mode_upsert_stores_without_duplicates(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.append(make_document(document_id="doc-001", title="Original"))
    source = StaticDocumentSource(
        [
            make_document(document_id="doc-001", title="Updated"),
            make_document(document_id="doc-002", title="New"),
        ]
    )

    result = ingest_documents(source, store, mode="upsert")

    assert result.fetched_count == 2
    assert result.stored_count == 2
    loaded = store.load_all()
    assert [document.document_id for document in loaded] == ["doc-001", "doc-002"]
    assert [document.title for document in loaded] == ["Updated", "New"]


def test_ingest_documents_invalid_mode_raises_clear_error(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    source = StaticDocumentSource([make_document()])

    with pytest.raises(ValueError, match="mode must be 'append' or 'upsert'"):
        ingest_documents(source, store, mode="replace")  # type: ignore[arg-type]


def test_ingestion_result_strips_empty_document_ids_and_errors() -> None:
    result = IngestionResult(
        source_name=" static ",
        fetched_count=1,
        stored_count=1,
        document_ids=[" doc-001 ", " ", ""],
        errors=[" first error ", " ", ""],
    )

    assert result.source_name == "static"
    assert result.document_ids == ["doc-001"]
    assert result.errors == ["first error"]


def test_ingestion_result_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        IngestionResult(source_name="static", fetched_count=-1, stored_count=0)


def test_ingestion_result_rejects_stored_count_exceeding_fetched_count() -> None:
    with pytest.raises(ValidationError, match="stored_count cannot exceed fetched_count"):
        IngestionResult(source_name="static", fetched_count=1, stored_count=2)


def test_ingestion_result_rejects_skipped_count_exceeding_fetched_count() -> None:
    with pytest.raises(ValidationError, match="skipped_count cannot exceed fetched_count"):
        IngestionResult(source_name="static", fetched_count=1, stored_count=1, skipped_count=2)
