from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from sentinel_research.agents.providers.base import BaseLLMProvider
from sentinel_research.agents.schemas import CseNewsAnalysis, MacroRiskLevel, SignalPolicy

_REQUIRED_FIELDS = (
    "schema_version, analysis_scope, ticker, sector, macro_risk_level, sentiment, "
    "catalyst_tags, affected_tickers, affected_sectors, signal_policy, "
    "manual_review_required, confidence, valid_until, staleness_risk, "
    "reason_codes, short_summary, sources"
)
_ENUM_CONTRACT = (
    "ENUM CONTRACT:\n"
    "- analysis_scope: MARKET, SECTOR, TICKER\n"
    "- macro_risk_level: LOW, MEDIUM, HIGH\n"
    "- sentiment: BULLISH, BEARISH, NEUTRAL, MIXED\n"
    "- signal_policy: SUPPORT, BLOCK, MANUAL_REVIEW, NO_EFFECT\n"
    "- staleness_risk: LOW, MEDIUM, HIGH\n"
    "- source_type: CBSL, CSE_DISCLOSURE, NEWS, DAILY_FT, OTHER"
)
_EXAMPLE_JSON = (
    '{"schema_version":"r10_news_analyst_v1","analysis_scope":"MARKET",'
    '"ticker":null,"sector":null,"macro_risk_level":"MEDIUM",'
    '"sentiment":"NEUTRAL","catalyst_tags":["MACRO"],"affected_tickers":[],'
    '"affected_sectors":["BANKING"],"signal_policy":"NO_EFFECT",'
    '"manual_review_required":false,"confidence":0.6,'
    '"valid_until":"2026-01-01T00:00:00Z","staleness_risk":"MEDIUM",'
    '"reason_codes":["INFO_ONLY"],'
    '"short_summary":"Macro update with limited immediate market impact.",'
    '"sources":[{"source_type":"CBSL","title":"Example source","url":null,'
    '"published_at":null,"retrieved_at":"2026-01-01T00:00:00Z"}]}'
)


def _json_prompt_value(value: Any) -> str:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def _normalize_source_type(value: Any) -> str:
    return str(getattr(value, "value", value)).strip()


def _normalize_source_title(value: Any) -> str:
    return str(value).strip()


def _normalize_source_url(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _source_identity(source: Any) -> tuple[str, str, str | None]:
    if hasattr(source, "source_type"):
        source_type = getattr(source, "source_type")
        title = getattr(source, "title")
        url = getattr(source, "url", None)
    else:
        source_type = source["source_type"]
        title = source["title"]
        url = source.get("url")
    return (
        _normalize_source_type(source_type),
        _normalize_source_title(title),
        _normalize_source_url(url),
    )


class R10AnalysisError(Exception):
    """Raised when R10 analysis output remains invalid after one repair retry."""


class R10OutputConsistencyError(ValueError):
    """Raised when validated R10 output violates deterministic policy rules."""


class ContextAgent:
    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    def process_document(self, document: str, sources: list[dict]) -> CseNewsAnalysis:
        if not document.strip():
            raise ValueError("document must not be empty")
        if not sources:
            raise ValueError("sources must not be empty")

        prompt = self._build_prompt(sources)
        raw_output = self._provider.analyze_context(document=document, prompt=prompt)

        try:
            analysis = self._validate_analysis_output(raw_output)
        except (ValidationError, R10OutputConsistencyError) as first_error:
            repair_prompt = self._build_repair_prompt(sources, str(first_error))
            repaired_output = self._provider.analyze_context(
                document=document,
                prompt=repair_prompt,
            )
            try:
                analysis = self._validate_analysis_output(repaired_output)
            except (ValidationError, R10OutputConsistencyError) as repair_error:
                raise R10AnalysisError(
                    "LLM output failed CseNewsAnalysis validation after one repair retry. "
                    f"first_error={first_error} repair_error={repair_error}"
                ) from repair_error
        self._assert_sources_match(analysis, sources)
        return analysis

    @classmethod
    def _validate_analysis_output(cls, raw_output: str) -> CseNewsAnalysis:
        analysis = CseNewsAnalysis.model_validate_json(raw_output)
        cls._validate_policy_consistency(analysis)
        return analysis

    @staticmethod
    def _validate_policy_consistency(analysis: CseNewsAnalysis) -> None:
        if analysis.signal_policy != SignalPolicy.NO_EFFECT:
            return

        inconsistency_reasons: list[str] = []
        if analysis.macro_risk_level in {MacroRiskLevel.MEDIUM, MacroRiskLevel.HIGH}:
            inconsistency_reasons.append("macro_risk_level MEDIUM/HIGH")
        if analysis.affected_tickers or analysis.affected_sectors:
            inconsistency_reasons.append("non-empty affected_tickers/affected_sectors")

        if inconsistency_reasons:
            reasons_text = " or ".join(inconsistency_reasons)
            raise R10OutputConsistencyError(
                "signal_policy NO_EFFECT is inconsistent with "
                f"{reasons_text}. Use MANUAL_REVIEW, SUPPORT, or BLOCK when the "
                "document has material market/sector/ticker impact."
            )

    @staticmethod
    def _assert_sources_match(analysis: CseNewsAnalysis, sources: list[dict]) -> None:
        allowed_sources = {_source_identity(source) for source in sources}
        unexpected_sources = [
            source for source in analysis.sources if _source_identity(source) not in allowed_sources
        ]
        if unexpected_sources:
            raise R10AnalysisError(
                "LLM output contained source entries not present in the provided input sources. "
                f"unexpected_sources={unexpected_sources!r}"
            )

    @staticmethod
    def _build_prompt(sources: list[dict]) -> str:
        sources_json = json.dumps(
            sources,
            ensure_ascii=True,
            separators=(",", ":"),
            default=_json_prompt_value,
        )
        return (
            "You are Sentinel-CSE R10 CSE News Analyst. Return JSON only.\n"
            'Use schema_version "r10_news_analyst_v1".\n'
            "R10 is context/risk only. Do not output buy/sell/hold/target price/"
            "order instructions.\n"
            "Every output must include the provided sources. Do not invent sources, "
            "URLs, or published_at values.\n"
            "If evidence is weak or unclear, use MANUAL_REVIEW.\n"
            "If the document has no meaningful market impact, use NO_EFFECT.\n"
            "Do not use synonyms.\n"
            "Do not use POSITIVE or NEGATIVE for sentiment.\n"
            'Do not use "CSE News Analysis" for analysis_scope.\n'
            "Use MARKET when analyzing market/macro-wide text.\n"
            "Use SECTOR only when a specific sector is the primary scope.\n"
            "Use TICKER only when a specific ticker is the primary scope.\n"
            f"{_ENUM_CONTRACT}\n"
            f"Required JSON fields: {_REQUIRED_FIELDS}.\n"
            f"Example JSON: {_EXAMPLE_JSON}\n"
            f"Provided sources JSON: {sources_json}"
        )

    @classmethod
    def _build_repair_prompt(cls, sources: list[dict], validation_error: str) -> str:
        return (
            f"{cls._build_prompt(sources)}\n"
            "Your previous response failed validation.\n"
            "Return the same schema again as JSON only.\n"
            "Replace invalid enum values with exact allowed enum values.\n"
            'Do not use synonyms like POSITIVE, NEGATIVE, CSE News Analysis, BUY, '
            "SELL, HOLD.\n"
            "Do not change or invent sources.\n"
            "Do not wrap JSON in markdown fences.\n"
            f"{_ENUM_CONTRACT}\n"
            f"Validation error: {validation_error}"
        )
