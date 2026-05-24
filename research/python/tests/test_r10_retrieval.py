from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import SourceDocument  # noqa: E402
from sentinel_research.agents.retrieval import (  # noqa: E402
    DocumentQuery,
    SimpleDocumentRetriever,
)


def make_document(**overrides: object) -> SourceDocument:
    payload = {
        "document_id": "doc-001",
        "source_type": "NEWS",
        "title": "General market update",
        "url": "https://example.com/doc-001",
        "published_at": "2026-05-23T09:00:00Z",
        "retrieved_at": "2026-05-23T10:00:00Z",
        "raw_text": "Liquidity conditions improved across the market.",
        "normalized_text": "Liquidity conditions improved across the market.",
        "tickers_hint": [],
        "sectors_hint": [],
        "metadata": {},
    }
    payload.update(overrides)
    return SourceDocument.model_validate(payload)


def make_retriever() -> SimpleDocumentRetriever:
    documents = [
        make_document(
            document_id="doc-title",
            title="CBSL rate hike surprises the market",
            raw_text="Macro bulletin with broad context.",
            normalized_text="Macro bulletin with broad context.",
            retrieved_at="2026-05-23T08:00:00Z",
        ),
        make_document(
            document_id="doc-raw",
            title="Liquidity update",
            raw_text="COMB.N0000 reported stronger earnings momentum.",
            normalized_text="Normal business update.",
            tickers_hint=[],
            retrieved_at="2026-05-23T09:00:00Z",
        ),
        make_document(
            document_id="doc-normalized",
            title="Travel outlook",
            raw_text="Travel operators issued updates.",
            normalized_text="Tourism recovery is accelerating in Sri Lanka.",
            retrieved_at="2026-05-23T07:00:00Z",
        ),
        make_document(
            document_id="doc-hints",
            source_type="CSE_DISCLOSURE",
            title="Banking company disclosure",
            raw_text="Company update with limited text.",
            normalized_text="Company update with limited text.",
            tickers_hint=["COMB.N0000"],
            sectors_hint=["BANKING"],
            retrieved_at="2026-05-23T11:00:00Z",
        ),
        make_document(
            document_id="doc-no-published",
            title="Undated note",
            published_at=None,
            retrieved_at="2026-05-23T12:00:00Z",
        ),
    ]
    return SimpleDocumentRetriever(documents)


def test_document_query_strips_empty_keywords_tickers_and_sectors() -> None:
    query = DocumentQuery(
        keywords=[" rate hike ", "   "],
        tickers=[" COMB.N0000 ", ""],
        sectors=[" BANKING ", " "],
    )

    assert query.keywords == ["rate hike"]
    assert query.tickers == ["COMB.N0000"]
    assert query.sectors == ["BANKING"]


def test_document_query_rejects_non_positive_limit() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        DocumentQuery(limit=0)


def test_empty_query_returns_most_recent_documents_limited() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(limit=2))

    assert [result.document.document_id for result in results] == [
        "doc-no-published",
        "doc-hints",
    ]


def test_keyword_search_finds_matches_in_title() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(keywords=["rate hike"]))

    assert [result.document.document_id for result in results] == ["doc-title"]


def test_keyword_search_finds_matches_in_raw_text() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(keywords=["stronger earnings"]))

    assert [result.document.document_id for result in results] == ["doc-raw"]


def test_keyword_search_finds_matches_in_normalized_text() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(keywords=["tourism recovery"]))

    assert [result.document.document_id for result in results] == ["doc-normalized"]


def test_ticker_search_matches_tickers_hint() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(tickers=["COMB.N0000"]))

    assert results[0].document.document_id == "doc-hints"


def test_ticker_search_matches_raw_text_occurrence() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(tickers=["COMB.N0000"], source_types=["NEWS"]))

    assert [result.document.document_id for result in results] == ["doc-raw"]


def test_sector_search_matches_sectors_hint() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(sectors=["BANKING"]))

    assert [result.document.document_id for result in results] == ["doc-hints"]


def test_source_type_filter_only_returns_matching_documents() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(source_types=["CSE_DISCLOSURE"]))

    assert [result.document.document_id for result in results] == ["doc-hints"]


def test_published_date_filters_exclude_out_of_range_and_missing_published_at() -> None:
    retriever = make_retriever()

    results = retriever.search(
        DocumentQuery(
            published_after="2026-05-23T08:30:00Z",
            published_before="2026-05-23T09:30:00Z",
        )
    )

    assert [result.document.document_id for result in results] == [
        "doc-hints",
        "doc-raw",
        "doc-title",
        "doc-normalized",
    ]
    assert all(result.document.document_id != "doc-no-published" for result in results)


def test_retrieved_date_filters_work() -> None:
    retriever = make_retriever()

    results = retriever.search(
        DocumentQuery(
            retrieved_after="2026-05-23T08:30:00Z",
            retrieved_before="2026-05-23T11:30:00Z",
        )
    )

    assert [result.document.document_id for result in results] == [
        "doc-hints",
        "doc-raw",
    ]


def test_results_sort_by_score_descending_then_retrieved_at_descending() -> None:
    retriever = SimpleDocumentRetriever(
        [
            make_document(
                document_id="older-high-score",
                title="Rate hike banking pressure",
                raw_text="Rate hike hits BANKING.",
                normalized_text="Rate hike hits BANKING.",
                sectors_hint=["BANKING"],
                retrieved_at="2026-05-23T09:00:00Z",
            ),
            make_document(
                document_id="newer-high-score",
                title="Rate hike banking pressure",
                raw_text="Rate hike hits BANKING.",
                normalized_text="Rate hike hits BANKING.",
                sectors_hint=["BANKING"],
                retrieved_at="2026-05-23T10:00:00Z",
            ),
            make_document(
                document_id="lower-score",
                title="Rate hike note",
                raw_text="Macro note only.",
                normalized_text="Macro note only.",
                sectors_hint=[],
                retrieved_at="2026-05-23T11:00:00Z",
            ),
        ]
    )

    results = retriever.search(DocumentQuery(keywords=["rate hike"], sectors=["BANKING"]))

    assert [result.document.document_id for result in results] == [
        "newer-high-score",
        "older-high-score",
        "lower-score",
    ]


def test_limit_is_respected() -> None:
    retriever = make_retriever()

    results = retriever.search(DocumentQuery(keywords=["update"], limit=1))

    assert len(results) == 1


def test_matched_reasons_are_populated() -> None:
    retriever = make_retriever()

    results = retriever.search(
        DocumentQuery(
            keywords=["banking"],
            sectors=["BANKING"],
            source_types=["CSE_DISCLOSURE"],
        )
    )

    top_reasons = results[0].matched_reasons if results else []

    assert top_reasons
    assert any(reason.startswith("keyword:") for reason in top_reasons)
    assert any(reason.startswith("source_type:") for reason in top_reasons)
