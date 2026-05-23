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
    DirectoryPdfDocumentSource,
    PdfExtractionError,
    PdfFileDocumentSource,
    ingest_documents,
)
from sentinel_research.agents.ingestion import pdf_source as pdf_source_module  # noqa: E402
from sentinel_research.agents.schemas import SourceType  # noqa: E402


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-pdf-source-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _make_fake_pdf_reader(
    *,
    page_texts_by_name: dict[str, list[str]] | None = None,
    error: Exception | None = None,
):
    class FakePdfReader:
        def __init__(self, handle) -> None:
            if error is not None:
                raise error
            texts = (page_texts_by_name or {}).get(Path(handle.name).name, [Path(handle.name).stem])
            self.pages = [_FakePdfPage(text) for text in texts]

    return FakePdfReader


@pytest.fixture
def patch_pypdf_reader(monkeypatch):
    def _patch(
        *,
        page_texts_by_name: dict[str, list[str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        monkeypatch.setattr(
            pdf_source_module,
            "_import_pypdf_reader",
            lambda: _make_fake_pdf_reader(
                page_texts_by_name=page_texts_by_name,
                error=error,
            ),
        )

    return _patch


def write_simple_pdf(path: Path, text: str) -> None:
    content_stream = f"BT\n/F1 12 Tf\n72 720 Td\n({_pdf_escape(text)}) Tj\nET\n".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            b"5 0 obj\n<< /Length "
            + str(len(content_stream)).encode("ascii")
            + b" >>\nstream\n"
            + content_stream
            + b"endstream\nendobj\n"
        ),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    startxref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{startxref}\n%%EOF"
        ).encode("ascii")
    )
    path.write_bytes(bytes(pdf))


def test_pdf_file_document_source_loads_local_pdf_into_source_document(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "CBSL policy update")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["CBSL policy update"]})

    source = PdfFileDocumentSource(pdf_path)
    documents = source.fetch()

    assert len(documents) == 1
    assert isinstance(documents[0], SourceDocument)
    assert "CBSL policy update" in documents[0].raw_text


def test_pdf_file_document_source_raises_file_not_found_for_missing_file(
    tmp_path: Path,
) -> None:
    source = PdfFileDocumentSource(tmp_path / "missing.pdf")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_pdf_file_document_source_raises_for_non_pdf_extension(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("not a pdf", encoding="utf-8")
    source = PdfFileDocumentSource(file_path)

    with pytest.raises(PdfExtractionError, match="Unsupported file extension"):
        source.fetch()


def test_pdf_file_document_source_raises_for_empty_unextractable_pdf_text(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "empty.pdf"
    write_simple_pdf(pdf_path, "   ")
    patch_pypdf_reader(page_texts_by_name={"empty.pdf": ["   ", "\n"]})
    source = PdfFileDocumentSource(pdf_path)

    with pytest.raises(PdfExtractionError, match="No extractable PDF text found"):
        source.fetch()


def test_pdf_file_document_source_wraps_pypdf_extraction_errors(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "broken.pdf"
    write_simple_pdf(pdf_path, "ignored")
    patch_pypdf_reader(error=RuntimeError("boom"))
    source = PdfFileDocumentSource(pdf_path)

    with pytest.raises(PdfExtractionError, match="Failed to extract PDF text from .*broken.pdf: boom"):
        source.fetch()


def test_pdf_file_document_source_uses_provided_metadata_fields(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "Dividend update")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["Dividend update"]})
    published_at = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
    source = PdfFileDocumentSource(
        pdf_path,
        source_type=SourceType.NEWS,
        title="Custom PDF Title",
        url="https://example.com/pdf",
        published_at=published_at,
        tickers_hint=["XYZ.N0000"],
        sectors_hint=["CONSUMER"],
    )
    document = source.fetch()[0]

    assert document.source_type == SourceType.NEWS
    assert document.title == "Custom PDF Title"
    assert str(document.url) == "https://example.com/pdf"
    assert document.published_at == published_at
    assert document.tickers_hint == ["XYZ.N0000"]
    assert document.sectors_hint == ["CONSUMER"]


def test_pdf_file_document_source_uses_injected_now_for_retrieved_at(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "CBSL policy update")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["CBSL policy update"]})
    fixed_now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    source = PdfFileDocumentSource(pdf_path, now=lambda: fixed_now)

    assert source.fetch()[0].retrieved_at == fixed_now


def test_pdf_file_document_source_metadata_includes_file_information(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "CBSL policy update")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["Page 1", "Page 2"]})
    source = PdfFileDocumentSource(pdf_path, metadata={"priority": 1})
    document = source.fetch()[0]

    assert document.metadata["file_path"] == str(pdf_path.resolve())
    assert document.metadata["file_name"] == "notice.pdf"
    assert document.metadata["ingestion_source"] == "pdf_file"
    assert document.metadata["page_count"] == 2
    assert document.metadata["priority"] == 1


def test_pdf_file_document_source_document_id_is_deterministic(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "CBSL policy update")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["CBSL policy update"]})
    source = PdfFileDocumentSource(pdf_path)

    first = source.fetch()[0].document_id
    second = source.fetch()[0].document_id

    assert first == second


def test_directory_pdf_document_source_loads_pdfs_in_sorted_order(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    write_simple_pdf(tmp_path / "b.pdf", "Second")
    write_simple_pdf(tmp_path / "a.pdf", "First")
    patch_pypdf_reader(
        page_texts_by_name={
            "a.pdf": ["First"],
            "b.pdf": ["Second"],
        }
    )

    source = DirectoryPdfDocumentSource(tmp_path)
    documents = source.fetch()

    assert [document.title for document in documents] == ["a", "b"]


def test_directory_pdf_document_source_returns_empty_list_when_no_matching_pdfs(
    tmp_path: Path,
) -> None:
    (tmp_path / "note.txt").write_text("not a pdf", encoding="utf-8")
    source = DirectoryPdfDocumentSource(tmp_path)

    assert source.fetch() == []


def test_directory_pdf_document_source_raises_file_not_found_for_missing_directory(
    tmp_path: Path,
) -> None:
    source = DirectoryPdfDocumentSource(tmp_path / "missing")

    with pytest.raises(FileNotFoundError):
        source.fetch()


def test_directory_pdf_document_source_can_be_used_with_ingest_documents_upsert(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    write_simple_pdf(tmp_path / "a.pdf", "First PDF")
    write_simple_pdf(tmp_path / "b.pdf", "Second PDF")
    patch_pypdf_reader(
        page_texts_by_name={
            "a.pdf": ["First PDF"],
            "b.pdf": ["Second PDF"],
        }
    )
    source = DirectoryPdfDocumentSource(
        tmp_path,
        source_type=SourceType.NEWS,
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


def test_pdf_file_document_source_can_be_used_with_ingest_documents_upsert(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    pdf_path = tmp_path / "notice.pdf"
    write_simple_pdf(pdf_path, "PDF content")
    patch_pypdf_reader(page_texts_by_name={"notice.pdf": ["PDF content"]})
    source = PdfFileDocumentSource(pdf_path, source_type=SourceType.CBSL)
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    first_result = ingest_documents(source, store, mode="upsert")
    second_result = ingest_documents(source, store, mode="upsert")
    loaded = store.load_all()

    assert first_result.stored_count == 1
    assert second_result.stored_count == 1
    assert len(loaded) == 1
    assert loaded[0].raw_text == "PDF content"
