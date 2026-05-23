from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.core import ContextAgent, R10AnalysisError  # noqa: E402
from sentinel_research.agents.providers.base import BaseLLMProvider  # noqa: E402
from sentinel_research.agents.schemas import CseNewsAnalysis  # noqa: E402

DOCUMENT = "CBSL kept rates unchanged while warning about external financing pressure."


class FakeProvider(BaseLLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def analyze_context(self, document: str, prompt: str) -> str:
        self.calls.append({"document": document, "prompt": prompt})
        if not self._responses:
            raise AssertionError("FakeProvider ran out of responses")
        return self._responses.pop(0)


def make_sources() -> list[dict[str, str]]:
    return [
        {
            "source_type": "NEWS",
            "title": "Daily FT market wrap",
            "url": "https://example.com/daily-ft-market-wrap",
            "published_at": "2026-05-22T10:00:00Z",
            "retrieved_at": "2026-05-22T10:30:00Z",
        }
    ]


def make_valid_payload() -> dict[str, object]:
    return {
        "schema_version": "r10_news_analyst_v1",
        "analysis_scope": "MARKET",
        "ticker": None,
        "sector": None,
        "macro_risk_level": "MEDIUM",
        "sentiment": "NEUTRAL",
        "catalyst_tags": ["MACRO"],
        "affected_tickers": [],
        "affected_sectors": ["BANKING"],
        "signal_policy": "NO_EFFECT",
        "manual_review_required": False,
        "confidence": 0.61,
        "valid_until": "2026-05-24T00:00:00Z",
        "staleness_risk": "MEDIUM",
        "reason_codes": ["INFO_ONLY"],
        "short_summary": "The document signals macro pressure but no direct trading action.",
        "sources": make_sources(),
    }


def test_valid_provider_json_returns_cse_news_analysis() -> None:
    provider = FakeProvider([json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert result.schema_version == "r10_news_analyst_v1"
    assert result.sources[0].title == "Daily FT market wrap"
    assert "Return JSON only." in provider.calls[0]["prompt"]
    assert "\"title\":\"Daily FT market wrap\"" in provider.calls[0]["prompt"]


def test_valid_output_with_matching_source_passes() -> None:
    provider = FakeProvider([json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert len(result.sources) == 1


def test_invalid_json_first_response_then_valid_repair_response_succeeds() -> None:
    provider = FakeProvider(["not-json", json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert "Validation error:" in provider.calls[1]["prompt"]


def test_invalid_json_twice_raises_r10_analysis_error() -> None:
    provider = FakeProvider(["not-json", "{still-not-json"])
    agent = ContextAgent(provider)

    with pytest.raises(R10AnalysisError, match="after one repair retry"):
        agent.process_document(DOCUMENT, make_sources())


def test_schema_invalid_json_first_response_then_valid_repair_response_succeeds() -> None:
    bad_payload = make_valid_payload()
    bad_payload["confidence"] = 1.5
    provider = FakeProvider([json.dumps(bad_payload), json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert "confidence" in provider.calls[1]["prompt"]


def test_empty_document_raises_value_error() -> None:
    agent = ContextAgent(FakeProvider([json.dumps(make_valid_payload())]))

    with pytest.raises(ValueError, match="document"):
        agent.process_document("   ", make_sources())


def test_empty_sources_raises_value_error() -> None:
    agent = ContextAgent(FakeProvider([json.dumps(make_valid_payload())]))

    with pytest.raises(ValueError, match="sources"):
        agent.process_document(DOCUMENT, [])


def test_provider_is_called_once_when_first_output_is_valid() -> None:
    provider = FakeProvider([json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    agent.process_document(DOCUMENT, make_sources())

    assert len(provider.calls) == 1
    assert provider.calls[0]["document"] == DOCUMENT


def test_provider_is_called_twice_when_repair_is_needed() -> None:
    bad_payload = make_valid_payload()
    bad_payload["signal_policy"] = "BUY"
    provider = FakeProvider([json.dumps(bad_payload), json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    agent.process_document(DOCUMENT, make_sources())

    assert len(provider.calls) == 2


def test_unsafe_buy_sell_language_from_provider_is_rejected_and_triggers_repair() -> None:
    bad_payload = make_valid_payload()
    bad_payload["short_summary"] = "Strong buy now because the stock should rally."
    provider = FakeProvider([json.dumps(bad_payload), json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert len(provider.calls) == 2
    assert "short_summary" in provider.calls[1]["prompt"]


def test_output_with_invented_url_raises_r10_analysis_error() -> None:
    bad_payload = make_valid_payload()
    bad_payload["sources"] = [{**make_sources()[0], "url": "https://example.com/invented"}]
    provider = FakeProvider([json.dumps(bad_payload)])
    agent = ContextAgent(provider)

    with pytest.raises(R10AnalysisError, match="not present in the provided input sources"):
        agent.process_document(DOCUMENT, make_sources())


def test_output_with_invented_title_raises_r10_analysis_error() -> None:
    bad_payload = make_valid_payload()
    bad_payload["sources"] = [{**make_sources()[0], "title": "Invented title"}]
    provider = FakeProvider([json.dumps(bad_payload)])
    agent = ContextAgent(provider)

    with pytest.raises(R10AnalysisError, match="not present in the provided input sources"):
        agent.process_document(DOCUMENT, make_sources())


def test_output_with_invented_source_type_raises_r10_analysis_error() -> None:
    bad_payload = make_valid_payload()
    bad_payload["sources"] = [{**make_sources()[0], "source_type": "OTHER"}]
    provider = FakeProvider([json.dumps(bad_payload)])
    agent = ContextAgent(provider)

    with pytest.raises(R10AnalysisError, match="not present in the provided input sources"):
        agent.process_document(DOCUMENT, make_sources())


def test_none_url_and_empty_string_url_are_treated_as_equivalent() -> None:
    input_sources = [{**make_sources()[0], "url": ""}]
    payload = make_valid_payload()
    payload["sources"] = [{**make_sources()[0], "url": None}]
    provider = FakeProvider([json.dumps(payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, input_sources)

    assert isinstance(result, CseNewsAnalysis)
