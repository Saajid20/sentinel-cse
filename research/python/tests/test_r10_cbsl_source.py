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
    CbslFetchError,
    CbslUrlDocumentSource,
    ingest_documents,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-cbsl-source-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


class FakeResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body


def test_constructor_rejects_empty_url_list() -> None:
    with pytest.raises(ValueError, match="at least one non-empty URL"):
        CbslUrlDocumentSource([])


def test_constructor_strips_urls_and_removes_empty_entries() -> None:
    captured_urls: list[str] = []

    def fake_http_get(url: str, **_: object) -> FakeResponse:
        captured_urls.append(url)
        return FakeResponse("<html><title>Test</title><body>Body text</body></html>")

    source = CbslUrlDocumentSource(["  https://cbsl.gov.lk/a  ", "  "], http_get=fake_http_get)
    source.fetch()

    assert captured_urls == ["https://cbsl.gov.lk/a"]


def test_fetch_returns_source_document_for_simple_html_with_title_and_body_text() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/notice"], http_get=fake_http_get)
    documents = source.fetch()

    assert len(documents) == 1
    assert isinstance(documents[0], SourceDocument)
    assert documents[0].title == "CBSL Notice"
    assert "Policy rate update text." in documents[0].raw_text


def test_source_document_has_cbsl_source_type() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/notice"], http_get=fake_http_get)

    assert source.fetch()[0].source_type.value == "CBSL"


def test_document_id_is_deterministic_for_same_url() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/notice"], http_get=fake_http_get)

    first = source.fetch()[0].document_id
    second = source.fetch()[0].document_id

    assert first == second


def test_retrieved_at_uses_injected_now() -> None:
    fixed_now = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)

    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(
        ["https://cbsl.gov.lk/notice"],
        now=lambda: fixed_now,
        http_get=fake_http_get,
    )

    assert source.fetch()[0].retrieved_at == fixed_now


def test_normalized_text_is_populated() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body> Policy   rate \n update text. </body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/notice"], http_get=fake_http_get)

    assert source.fetch()[0].normalized_text == "Policy rate update text."


def test_fetch_raises_cbsl_fetch_error_for_empty_extracted_text() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><head><title>Empty</title></head><body><script>var x = 1;</script></body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/empty"], http_get=fake_http_get)

    with pytest.raises(CbslFetchError, match="https://cbsl.gov.lk/empty"):
        source.fetch()


def test_fetch_raises_cbsl_fetch_error_for_non_200_response() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><body>Not found</body></html>", status=404)

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/missing"], http_get=fake_http_get)

    with pytest.raises(CbslFetchError, match="HTTP 404"):
        source.fetch()


def test_multiple_urls_return_multiple_source_documents_in_input_order() -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        title = "First" if url.endswith("/1") else "Second"
        return FakeResponse(f"<html><title>{title}</title><body>{title} body text.</body></html>")

    source = CbslUrlDocumentSource(
        ["https://cbsl.gov.lk/1", "https://cbsl.gov.lk/2"],
        http_get=fake_http_get,
    )
    documents = source.fetch()

    assert [document.title for document in documents] == ["First", "Second"]


def test_http_get_fake_is_called_with_url_timeout_and_user_agent() -> None:
    calls: list[dict[str, object]] = []

    def fake_http_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(
        ["https://cbsl.gov.lk/notice"],
        timeout=12.5,
        user_agent="Sentinel-Test-Agent/1.0",
        http_get=fake_http_get,
    )
    source.fetch()

    assert calls == [
        {
            "url": "https://cbsl.gov.lk/notice",
            "timeout": 12.5,
            "user_agent": "Sentinel-Test-Agent/1.0",
        }
    ]


def test_cbsl_url_document_source_can_be_used_with_ingest_documents_upsert(
    tmp_path: Path,
) -> None:
    def fake_http_get(url: str, **_: object) -> FakeResponse:
        return FakeResponse("<html><title>CBSL Notice</title><body>Policy rate update text.</body></html>")

    source = CbslUrlDocumentSource(["https://cbsl.gov.lk/notice"], http_get=fake_http_get)
    store = LocalDocumentStore(tmp_path / "documents.jsonl")

    first_result = ingest_documents(source, store, mode="upsert")
    second_result = ingest_documents(source, store, mode="upsert")
    loaded = store.load_all()

    assert first_result.stored_count == 1
    assert second_result.stored_count == 1
    assert len(loaded) == 1
    assert loaded[0].source_type.value == "CBSL"
