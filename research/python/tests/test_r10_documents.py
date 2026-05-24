from __future__ import annotations

import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import (  # noqa: E402
    LocalDocumentStore,
    SourceDocument,
    build_normalized_text,
    normalize_whitespace,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-documents-{uuid4().hex}"
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
        "metadata": {"priority": 1, "verified": True},
    }
    payload.update(overrides)
    return SourceDocument.model_validate(payload)


def test_source_document_accepts_valid_data() -> None:
    document = make_document()

    assert document.document_id == "doc-001"
    assert document.source_type.value == "NEWS"
    assert document.tickers_hint == ["COMB.N0000"]


def test_source_document_strips_whitespace_and_normalizes_empty_url() -> None:
    document = make_document(
        document_id="  doc-002  ",
        title="  CBSL bulletin  ",
        url="   ",
        raw_text="  Liquidity improved.  ",
        normalized_text="   ",
        tickers_hint=["  COMB.N0000  ", "   "],
        sectors_hint=["  BANKING  ", ""],
    )

    assert document.document_id == "doc-002"
    assert document.title == "CBSL bulletin"
    assert document.url is None
    assert document.raw_text == "Liquidity improved."
    assert document.normalized_text is None
    assert document.tickers_hint == ["COMB.N0000"]
    assert document.sectors_hint == ["BANKING"]


def test_source_document_rejects_empty_document_id() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_document(document_id="   ")


def test_source_document_rejects_empty_title() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_document(title="   ")


def test_source_document_rejects_empty_raw_text() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_document(raw_text="   ")


def test_normalize_whitespace_collapses_repeated_whitespace_and_newlines() -> None:
    text = "  First line\r\n\r\nSecond\t\tline \n   Third line  "

    assert normalize_whitespace(text) == "First line Second line Third line"


def test_build_normalized_text_returns_cleaned_text_without_summarizing() -> None:
    raw_text = "  CBSL kept policy rates unchanged,\r\nwhile warning about inflation.  "

    assert build_normalized_text(raw_text) == (
        "CBSL kept policy rates unchanged, while warning about inflation."
    )


def test_local_document_store_append_and_load_all_roundtrips_one_document(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()

    store.append(document)
    loaded = store.load_all()

    assert loaded == [document]


def test_local_document_store_append_many_and_load_all_roundtrips_multiple_documents(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    documents = [
        make_document(document_id="doc-001"),
        make_document(document_id="doc-002", title="Second document"),
    ]

    store.append_many(documents)
    loaded = store.load_all()

    assert loaded == documents


def test_local_document_store_load_all_returns_empty_list_for_missing_file(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "missing.jsonl")

    assert store.load_all() == []


def test_local_document_store_raises_value_error_with_line_number_for_invalid_jsonl(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "documents.jsonl"
    valid_line = make_document().model_dump_json()
    store_path.write_text(f"{valid_line}\n{{not-json}}\n", encoding="utf-8")
    store = LocalDocumentStore(store_path)

    with pytest.raises(ValueError, match="line 2"):
        store.load_all()


def test_local_document_store_clear_removes_only_jsonl_file(tmp_path: Path) -> None:
    parent = tmp_path / "nested"
    store = LocalDocumentStore(parent / "documents.jsonl")
    store.append(make_document())

    store.clear()

    assert not (parent / "documents.jsonl").exists()
    assert parent.exists()


def test_local_document_store_exists_returns_true_for_stored_document_id(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.append(make_document())

    assert store.exists("doc-001") is True


def test_local_document_store_exists_returns_false_for_missing_document_id(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.append(make_document())

    assert store.exists("doc-999") is False


def test_local_document_store_exists_rejects_empty_document_id(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    with pytest.raises(ValueError, match="document_id must not be empty"):
        store.exists("   ")


def test_local_document_store_load_by_id_returns_matching_document(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()
    store.append(document)

    assert store.load_by_id("  doc-001  ") == document


def test_local_document_store_load_by_id_returns_none_for_missing_document(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.append(make_document())

    assert store.load_by_id("doc-999") is None


def test_local_document_store_load_by_id_rejects_empty_document_id(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    with pytest.raises(ValueError, match="document_id must not be empty"):
        store.load_by_id(" ")


def test_local_document_store_upsert_inserts_new_document(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()

    store.upsert(document)

    assert store.load_all() == [document]


def test_local_document_store_upsert_replaces_existing_document_without_duplicates(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    original = make_document()
    replacement = make_document(title="Updated title", raw_text="Updated raw text.")
    store.append(original)

    store.upsert(replacement)
    loaded = store.load_all()

    assert loaded == [replacement]
    assert len(loaded) == 1


def test_local_document_store_upsert_replacement_preserves_original_position(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    first = make_document(document_id="doc-001", title="First")
    second = make_document(document_id="doc-002", title="Second")
    replacement = make_document(document_id="doc-001", title="First updated")
    store.append_many([first, second])

    store.upsert(replacement)

    assert [document.document_id for document in store.load_all()] == ["doc-001", "doc-002"]
    assert store.load_all()[0].title == "First updated"


def test_local_document_store_upsert_many_inserts_multiple_documents(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    documents = [
        make_document(document_id="doc-001"),
        make_document(document_id="doc-002", title="Second"),
    ]

    store.upsert_many(documents)

    assert store.load_all() == documents


def test_local_document_store_upsert_many_duplicate_input_last_one_wins(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    first = make_document(document_id="doc-001", title="First version")
    last = make_document(document_id="doc-001", title="Last version")

    store.upsert_many([first, last])

    loaded = store.load_all()
    assert loaded == [last]


def test_local_document_store_upsert_many_does_not_duplicate_existing_document_ids(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    existing = make_document(document_id="doc-001", title="Existing")
    updated_existing = make_document(document_id="doc-001", title="Updated existing")
    new_document = make_document(document_id="doc-002", title="New document")
    store.append(existing)

    store.upsert_many([updated_existing, new_document])

    loaded = store.load_all()
    assert [document.document_id for document in loaded] == ["doc-001", "doc-002"]
    assert loaded[0].title == "Updated existing"
    assert loaded[1].title == "New document"


def test_local_document_store_upsert_raises_value_error_for_invalid_existing_jsonl(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "documents.jsonl"
    store_path.write_text("{not-json}\n", encoding="utf-8")
    store = LocalDocumentStore(store_path)

    with pytest.raises(ValueError, match="Invalid JSON in document store at line 1"):
        store.upsert(make_document())


def test_local_document_store_append_remains_append_only_and_can_create_duplicates(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    first = make_document(document_id="doc-001", title="First version")
    duplicate = make_document(document_id="doc-001", title="Duplicate version")

    store.append(first)
    store.append(duplicate)

    loaded = store.load_all()
    assert len(loaded) == 2
    assert [document.title for document in loaded] == ["First version", "Duplicate version"]


def test_local_document_store_load_all_still_works_after_upsert_operations(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.upsert(make_document(document_id="doc-001", title="First"))
    store.upsert_many(
        [
            make_document(document_id="doc-002", title="Second"),
            make_document(document_id="doc-001", title="First updated"),
        ]
    )

    loaded = store.load_all()
    assert [document.document_id for document in loaded] == ["doc-001", "doc-002"]
    assert [document.title for document in loaded] == ["First updated", "Second"]
