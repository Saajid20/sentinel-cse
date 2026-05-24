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


def make_valid_payload(**overrides: object) -> dict[str, object]:
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
        "confidence": 0.61,
        "valid_until": "2026-05-24T00:00:00Z",
        "staleness_risk": "MEDIUM",
        "reason_codes": ["INFO_ONLY"],
        "short_summary": "The document signals macro pressure and should be reviewed.",
        "sources": make_sources(),
    }
    payload.update(overrides)
    return payload


def test_valid_provider_json_returns_cse_news_analysis() -> None:
    provider = FakeProvider([json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert result.schema_version == "r10_news_analyst_v1"
    assert result.sources[0].title == "Daily FT market wrap"
    assert "Return JSON only." in provider.calls[0]["prompt"]
    assert "ENUM CONTRACT:" in provider.calls[0]["prompt"]
    assert "analysis_scope: MARKET, SECTOR, TICKER" in provider.calls[0]["prompt"]
    assert "sentiment: BULLISH, BEARISH, NEUTRAL, MIXED" in provider.calls[0]["prompt"]
    assert '"analysis_scope":"MARKET"' in provider.calls[0]["prompt"]
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
    assert "ENUM CONTRACT:" in provider.calls[1]["prompt"]
    assert "Replace invalid enum values with exact allowed enum values." in provider.calls[1]["prompt"]
    assert "POSITIVE, NEGATIVE, CSE News Analysis, BUY, SELL, HOLD" in provider.calls[1]["prompt"]


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


def test_repair_prompt_warns_against_positive_and_cse_news_analysis() -> None:
    bad_payload = make_valid_payload()
    bad_payload["analysis_scope"] = "CSE News Analysis"
    provider = FakeProvider([json.dumps(bad_payload), json.dumps(make_valid_payload())])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert "CSE News Analysis" in provider.calls[1]["prompt"]
    assert "POSITIVE" in provider.calls[1]["prompt"]


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


def test_no_effect_with_medium_macro_risk_triggers_repair_and_succeeds() -> None:
    inconsistent_payload = make_valid_payload(
        macro_risk_level="MEDIUM",
        affected_sectors=[],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
    )
    repaired_payload = make_valid_payload(
        macro_risk_level="MEDIUM",
        affected_sectors=[],
        signal_policy="MANUAL_REVIEW",
        manual_review_required=True,
    )
    provider = FakeProvider([json.dumps(inconsistent_payload), json.dumps(repaired_payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert result.signal_policy.value == "MANUAL_REVIEW"
    assert len(provider.calls) == 2


def test_no_effect_with_high_macro_risk_triggers_repair() -> None:
    inconsistent_payload = make_valid_payload(
        macro_risk_level="HIGH",
        affected_sectors=[],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
    )
    repaired_payload = make_valid_payload(
        macro_risk_level="HIGH",
        affected_sectors=[],
        signal_policy="MANUAL_REVIEW",
        manual_review_required=True,
    )
    provider = FakeProvider([json.dumps(inconsistent_payload), json.dumps(repaired_payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert len(provider.calls) == 2


def test_no_effect_with_non_empty_affected_sectors_triggers_repair() -> None:
    inconsistent_payload = make_valid_payload(
        macro_risk_level="LOW",
        affected_sectors=["BANKING"],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
    )
    repaired_payload = make_valid_payload(
        macro_risk_level="LOW",
        affected_sectors=["BANKING"],
        signal_policy="MANUAL_REVIEW",
        manual_review_required=True,
    )
    provider = FakeProvider([json.dumps(inconsistent_payload), json.dumps(repaired_payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert len(provider.calls) == 2


def test_no_effect_with_low_risk_and_no_affected_entities_passes() -> None:
    payload = make_valid_payload(
        macro_risk_level="LOW",
        affected_tickers=[],
        affected_sectors=[],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
        short_summary="The document is informational with no material market impact.",
    )
    provider = FakeProvider([json.dumps(payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert result.signal_policy.value == "NO_EFFECT"
    assert len(provider.calls) == 1


def test_inconsistent_no_effect_after_repair_raises_r10_analysis_error() -> None:
    inconsistent_payload = make_valid_payload(
        macro_risk_level="MEDIUM",
        affected_sectors=[],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
    )
    provider = FakeProvider([json.dumps(inconsistent_payload), json.dumps(inconsistent_payload)])
    agent = ContextAgent(provider)

    with pytest.raises(R10AnalysisError, match="after one repair retry"):
        agent.process_document(DOCUMENT, make_sources())


def test_policy_consistency_repair_prompt_includes_error_message() -> None:
    inconsistent_payload = make_valid_payload(
        macro_risk_level="MEDIUM",
        affected_sectors=[],
        signal_policy="NO_EFFECT",
        manual_review_required=False,
    )
    repaired_payload = make_valid_payload(
        macro_risk_level="MEDIUM",
        affected_sectors=[],
        signal_policy="MANUAL_REVIEW",
        manual_review_required=True,
    )
    provider = FakeProvider([json.dumps(inconsistent_payload), json.dumps(repaired_payload)])
    agent = ContextAgent(provider)

    result = agent.process_document(DOCUMENT, make_sources())

    assert isinstance(result, CseNewsAnalysis)
    assert (
        "signal_policy NO_EFFECT is inconsistent with macro_risk_level"
        in provider.calls[1]["prompt"]
    )
    assert (
        "Use MANUAL_REVIEW, SUPPORT, or BLOCK when the document has material "
        "market/sector/ticker impact."
        in provider.calls[1]["prompt"]
    )
