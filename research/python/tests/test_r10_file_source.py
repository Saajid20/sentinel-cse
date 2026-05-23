from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    DirectoryTextDocumentSource,
    ManualFileIngestionError,
    TextFileDocumentSource,
    ingest_documents,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-file-source-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_text_file_document_source_loads_txt_into_source_document(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    write_text(file_path, "CBSL market note")

    source = TextFileDocumentSource(file_path)
    documents = source.fetch()

    assert len(documents) == 1
    assert isinstance(documents[0], SourceDocument)
    assert documents[0].raw_text == "CBSL market note"


def test_text_file_document_source_loads_md_into_source_document(tmp_path: Path) -> None:
    file_path = tmp_path / "note.md"
    write_text(file_path, "# Heading\n\nCBSL market note")

    source = TextFileDocumentSource(file_path)

    assert source.fetch()[0].raw_text == "# Heading\n\nCBSL market note"


def test_text_file_document_source_extracts_visible_text_from_html(tmp_path: Path) -> None:
    file_path = tmp_path / "note.html"
    write_text(
        file_path,
        "<html><head><style>.x{display:none}</style><script>var x=1;</script></head>"
        "<body><h1>Heading</h1><p>Visible body text.</p></body></html>",
    )

    source = TextFileDocumentSource(file_path)
    document = source.fetch()[0]

    assert document.raw_text == "Heading Visible body text."
    assert "var x=1" not in document.raw_text
    assert ".x{display:none}" not in document.raw_text


def test_text_file_document_source_raises_file_not_found_for_missing_file(
    tmp_path: Path,
) -> None:
    source = TextFileDocumentSource(tmp_path / "missing.txt")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_text_file_document_source_raises_for_unsupported_extension(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "note.csv"
    write_text(file_path, "a,b,c")
    source = TextFileDocumentSource(file_path)

    with pytest.raises(ManualFileIngestionError, match="Unsupported file extension"):
        source.fetch()


def test_text_file_document_source_raises_for_empty_extracted_text(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.html"
    write_text(file_path, "<html><body><script>var x=1;</script></body></html>")
    source = TextFileDocumentSource(file_path)

    with pytest.raises(ManualFileIngestionError, match="No usable text extracted"):
        source.fetch()


def test_text_file_document_source_uses_provided_metadata_fields(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    write_text(file_path, "CBSL market note")
    published_at = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
    source = TextFileDocumentSource(
        file_path,
        source_type="NEWS",
        title="Custom title",
        url="https://example.com/doc",
        published_at=published_at,
        tickers_hint=["COMB.N0000"],
        sectors_hint=["BANKING"],
    )
    document = source.fetch()[0]

    assert document.source_type.value == "NEWS"
    assert document.title == "Custom title"
    assert str(document.url) == "https://example.com/doc"
    assert document.published_at == published_at
    assert document.tickers_hint == ["COMB.N0000"]
    assert document.sectors_hint == ["BANKING"]


def test_text_file_document_source_uses_injected_now_for_retrieved_at(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "note.txt"
    write_text(file_path, "CBSL market note")
    fixed_now = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    source = TextFileDocumentSource(file_path, now=lambda: fixed_now)

    assert source.fetch()[0].retrieved_at == fixed_now


def test_text_file_document_source_metadata_includes_file_information(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "note.txt"
    write_text(file_path, "CBSL market note")
    source = TextFileDocumentSource(file_path, metadata={"priority": 1})
    document = source.fetch()[0]

    assert document.metadata["file_path"] == str(file_path.resolve())
    assert document.metadata["file_name"] == "note.txt"
    assert document.metadata["ingestion_source"] == "manual_file"
    assert document.metadata["priority"] == 1


def test_text_file_document_source_document_id_is_deterministic(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    write_text(file_path, "CBSL market note")
    source = TextFileDocumentSource(file_path)

    first = source.fetch()[0].document_id
    second = source.fetch()[0].document_id

    assert first == second


def test_directory_text_document_source_loads_supported_files_in_sorted_order(
    tmp_path: Path,
) -> None:
    write_text(tmp_path / "b.txt", "Second")
    write_text(tmp_path / "a.md", "First")

    source = DirectoryTextDocumentSource(tmp_path)
    documents = source.fetch()

    assert [document.title for document in documents] == ["a", "b"]


def test_directory_text_document_source_skips_unsupported_files(tmp_path: Path) -> None:
    write_text(tmp_path / "supported.txt", "Supported")
    write_text(tmp_path / "ignored.csv", "Ignored")

    source = DirectoryTextDocumentSource(tmp_path)

    assert [document.title for document in source.fetch()] == ["supported"]


def test_directory_text_document_source_returns_empty_list_when_no_supported_files(
    tmp_path: Path,
) -> None:
    write_text(tmp_path / "ignored.csv", "Ignored")

    source = DirectoryTextDocumentSource(tmp_path, pattern="*.csv")

    assert source.fetch() == []


def test_directory_text_document_source_raises_file_not_found_for_missing_directory(
    tmp_path: Path,
) -> None:
    source = DirectoryTextDocumentSource(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_directory_text_document_source_can_be_used_with_ingest_documents_upsert(
    tmp_path: Path,
) -> None:
    write_text(tmp_path / "a.txt", "First")
    write_text(tmp_path / "b.html", "<html><body>Second</body></html>")
    source = DirectoryTextDocumentSource(
        tmp_path,
        source_type="NEWS",
        default_tickers_hint=["COMB.N0000"],
        default_sectors_hint=["BANKING"],
    )
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    first_result = ingest_documents(source, store, mode="upsert")
    second_result = ingest_documents(source, store, mode="upsert")
    loaded = store.load_all()

    assert first_result.stored_count == 2
    assert second_result.stored_count == 2
    assert len(loaded) == 2
    assert [document.title for document in loaded] == ["a", "b"]
