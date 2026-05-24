from __future__ import annotations

import json
import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.analysis import RetrievedContextAnalyzer  # noqa: E402
from sentinel_research.agents.core import ContextAgent  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument  # noqa: E402
from sentinel_research.agents.providers.base import BaseLLMProvider  # noqa: E402
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402
from sentinel_research.agents.schemas import CseNewsAnalysis  # noqa: E402


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-analyzer-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


class FakeProvider(BaseLLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def analyze_context(self, document: str, prompt: str) -> str:
        self.calls.append({"document": document, "prompt": prompt})
        if not self._responses:
            raise AssertionError("FakeProvider ran out of responses")
        return self._responses.pop(0)


def make_document(**overrides: object) -> SourceDocument:
    payload = {
        "document_id": "doc-001",
        "source_type": "NEWS",
        "title": "CBSL market update",
        "url": "https://example.com/doc-001",
        "published_at": "2026-05-23T09:00:00Z",
        "retrieved_at": "2026-05-23T10:00:00Z",
        "raw_text": "CBSL said liquidity conditions are improving.",
        "normalized_text": "CBSL said liquidity conditions are improving.",
        "tickers_hint": ["COMB.N0000"],
        "sectors_hint": ["BANKING"],
        "metadata": {},
    }
    payload.update(overrides)
    return SourceDocument.model_validate(payload)


def make_analysis_payload(sources: list[dict], **overrides: object) -> dict[str, object]:
    payload = {
        "schema_version": "r10_news_analyst_v1",
        "analysis_scope": "MARKET",
        "ticker": None,
        "sector": None,
        "macro_risk_level": "MEDIUM",
        "sentiment": "NEUTRAL",
        "catalyst_tags": ["MACRO"],
        "affected_tickers": [],
        "affected_sectors": ["BANKING"],
        "signal_policy": "MANUAL_REVIEW",
        "manual_review_required": True,
        "confidence": 0.62,
        "valid_until": "2026-05-24T00:00:00Z",
        "staleness_risk": "MEDIUM",
        "reason_codes": ["INFO_ONLY"],
        "short_summary": "Retrieved local context suggests a macro review is required.",
        "sources": sources,
    }
    payload.update(overrides)
    return payload


def make_sources_from_documents(documents: list[SourceDocument]) -> list[dict]:
    return [
        {
            "source_type": document.source_type.value,
            "title": document.title,
            "url": document.url,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "retrieved_at": document.retrieved_at.isoformat(),
        }
        for document in documents
    ]


def test_analyze_loads_documents_retrieves_matching_document_and_returns_analysis(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()
    store.append(document)
    sources = make_sources_from_documents([document])
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    result = analyzer.analyze(DocumentQuery(keywords=["liquidity"]))

    assert isinstance(result, CseNewsAnalysis)
    assert result.sources[0].title == document.title
    assert len(provider.calls) == 1


def test_empty_store_raises_value_error(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    analyzer = RetrievedContextAnalyzer(
        store,
        ContextAgent(FakeProvider([])),
    )

    with pytest.raises(ValueError, match="contains no documents"):
        analyzer.analyze(DocumentQuery(keywords=["anything"]))


def test_query_with_no_matches_raises_value_error(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    store.append(make_document())
    analyzer = RetrievedContextAnalyzer(
        store,
        ContextAgent(FakeProvider([])),
    )

    with pytest.raises(ValueError, match="No documents matched"):
        analyzer.analyze(DocumentQuery(keywords=["nonexistent"]))


def test_combined_document_includes_required_fields(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()
    store.append(document)
    sources = make_sources_from_documents([document])
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    analyzer.analyze(DocumentQuery(keywords=["liquidity"]))

    combined_document = provider.calls[0]["document"]
    assert "document_id: doc-001" in combined_document
    assert f"title: {document.title}" in combined_document
    assert "source_type: NEWS" in combined_document
    assert "score: 1.0" in combined_document
    assert 'matched_reasons: ["keyword:liquidity"]' in combined_document
    assert "CBSL said liquidity conditions are improving." in combined_document


def test_sources_passed_to_context_agent_preserve_source_type_title_and_url(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document(
        source_type="CSE_DISCLOSURE",
        title="Issuer disclosure",
        url="https://example.com/disclosure",
    )
    store.append(document)
    sources = make_sources_from_documents([document])
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    result = analyzer.analyze(DocumentQuery(source_types=["CSE_DISCLOSURE"]))

    assert result.sources[0].source_type.value == "CSE_DISCLOSURE"
    assert result.sources[0].title == "Issuer disclosure"
    assert str(result.sources[0].url) == "https://example.com/disclosure"


def test_multiple_retrieved_documents_are_included_in_deterministic_order(
    tmp_path: Path,
) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    first = make_document(
        document_id="doc-older",
        title="Older banking note",
        raw_text="BANKING sector update.",
        normalized_text="BANKING sector update.",
        retrieved_at="2026-05-23T09:00:00Z",
    )
    second = make_document(
        document_id="doc-newer",
        title="Newer banking note",
        raw_text="BANKING sector update.",
        normalized_text="BANKING sector update.",
        retrieved_at="2026-05-23T11:00:00Z",
    )
    store.append_many([first, second])
    ordered_documents = [second, first]
    sources = make_sources_from_documents(ordered_documents)
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    analyzer.analyze(DocumentQuery(keywords=["banking"]))

    combined_document = provider.calls[0]["document"]
    assert combined_document.index("--- DOCUMENT 1 ---") < combined_document.index("--- DOCUMENT 2 ---")
    assert combined_document.index("document_id: doc-newer") < combined_document.index(
        "document_id: doc-older"
    )


def test_query_limit_is_respected(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    documents = [
        make_document(
            document_id="doc-1",
            title="Banking note 1",
            raw_text="BANKING sector update.",
            normalized_text="BANKING sector update.",
            retrieved_at="2026-05-23T09:00:00Z",
        ),
        make_document(
            document_id="doc-2",
            title="Banking note 2",
            raw_text="BANKING sector update.",
            normalized_text="BANKING sector update.",
            retrieved_at="2026-05-23T10:00:00Z",
        ),
        make_document(
            document_id="doc-3",
            title="Banking note 3",
            raw_text="BANKING sector update.",
            normalized_text="BANKING sector update.",
            retrieved_at="2026-05-23T11:00:00Z",
        ),
    ]
    store.append_many(documents)
    sources = make_sources_from_documents([documents[2]])
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    analyzer.analyze(DocumentQuery(keywords=["banking"], limit=1))

    combined_document = provider.calls[0]["document"]
    assert combined_document.count("--- DOCUMENT") == 1
    assert "document_id: doc-3" in combined_document


def test_tests_use_fake_provider_only_and_never_call_deepseek(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path / "documents.jsonl")
    document = make_document()
    store.append(document)
    sources = make_sources_from_documents([document])
    provider = FakeProvider([json.dumps(make_analysis_payload(sources))])
    analyzer = RetrievedContextAnalyzer(store, ContextAgent(provider))

    analyzer.analyze(DocumentQuery(keywords=["liquidity"]))

    assert len(provider.calls) == 1
