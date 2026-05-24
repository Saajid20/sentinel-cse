from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sentinel_research.agents.normalization import (
    is_shareholder_or_takeover_disclosure,
    normalize_catalyst_tags,
)
from sentinel_research.agents.reports import R10AnalysisReport


class StrategyCandidateType(str, Enum):
    VWAP_VOLUME_SPREAD_READY = "VWAP_VOLUME_SPREAD_READY"
    MOMENTUM_BREAKOUT_READY = "MOMENTUM_BREAKOUT_READY"
    MEAN_REVERSION_READY = "MEAN_REVERSION_READY"
    LIQUIDITY_WATCHLIST = "LIQUIDITY_WATCHLIST"
    UNKNOWN = "UNKNOWN"


class R10DecisionPolicy(str, Enum):
    SUPPORT = "SUPPORT"
    BLOCK = "BLOCK"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_EFFECT = "NO_EFFECT"


class TechnicalSignalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    ticker: str
    strategy_candidate_type: StrategyCandidateType
    detected_at: datetime
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate_id must not be empty")
        return normalized

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be empty")
        return normalized

    @field_validator("detected_at")
    @classmethod
    def _validate_detected_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at must be timezone-aware")
        return value


class R10PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "r10_policy_decision_v1"
    candidate_id: str
    ticker: str
    strategy_candidate_type: StrategyCandidateType
    r10_report_id: str
    r10_policy: R10DecisionPolicy
    manual_review_required: bool
    reason_codes: list[str]
    source_report_type: str
    source_analysis_scope: str
    source_macro_risk_level: str
    source_sentiment: str
    normalized_catalyst_tags: list[str]
    generated_at: datetime
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "r10_policy_decision_v1":
            raise ValueError(
                f'schema_version must be "r10_policy_decision_v1", got {value!r}'
            )
        return value

    @field_validator("candidate_id", "ticker", "r10_report_id")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("generated_at")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @field_validator("reason_codes", "normalized_catalyst_tags")
    @classmethod
    def _normalize_list_items(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
        return normalized

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


def evaluate_r10_policy(
    candidate: TechnicalSignalCandidate,
    report: R10AnalysisReport,
    *,
    generated_at: datetime | None = None,
) -> R10PolicyDecision:
    normalized_catalyst_tags = normalize_catalyst_tags(report.analysis.catalyst_tags)
    final_policy = R10DecisionPolicy(report.analysis.signal_policy.value)
    deterministic_reason_codes: list[str] = []

    if report.analysis.manual_review_required:
        deterministic_reason_codes.append("R10_ANALYSIS_MANUAL_REVIEW_REQUIRED")
        if final_policy is not R10DecisionPolicy.BLOCK:
            final_policy = R10DecisionPolicy.MANUAL_REVIEW

    if report.analysis.macro_risk_level.value == "HIGH":
        deterministic_reason_codes.append("R10_HIGH_MACRO_RISK_BLOCK")
        final_policy = R10DecisionPolicy.BLOCK

    if report.analysis.signal_policy.value == "BLOCK":
        deterministic_reason_codes.append("R10_ANALYSIS_BLOCK")
        final_policy = R10DecisionPolicy.BLOCK

    if is_shareholder_or_takeover_disclosure(
        report.analysis.catalyst_tags,
        reason_codes=report.analysis.reason_codes,
        short_summary=report.analysis.short_summary,
    ):
        deterministic_reason_codes.append("R10_SHAREHOLDER_ACTIVITY_REVIEW")
        if final_policy is R10DecisionPolicy.SUPPORT:
            final_policy = R10DecisionPolicy.MANUAL_REVIEW

    report_ticker = (report.analysis.ticker or "").strip().upper()
    if report_ticker and candidate.ticker != report_ticker:
        deterministic_reason_codes.append("R10_TICKER_MISMATCH_REVIEW")
        if final_policy is not R10DecisionPolicy.BLOCK:
            final_policy = R10DecisionPolicy.MANUAL_REVIEW

    if final_policy is R10DecisionPolicy.SUPPORT:
        manual_review_required = report.analysis.manual_review_required
    elif final_policy in (R10DecisionPolicy.MANUAL_REVIEW, R10DecisionPolicy.BLOCK):
        manual_review_required = True
    else:
        manual_review_required = report.analysis.manual_review_required

    reason_codes = _dedupe_preserving_order(
        deterministic_reason_codes
        + [f"ANALYSIS_{code.strip()}" for code in report.analysis.reason_codes if code.strip()]
    )
    if not reason_codes:
        reason_codes = ["R10_POLICY_NO_EFFECT"]

    return R10PolicyDecision(
        candidate_id=candidate.candidate_id,
        ticker=candidate.ticker,
        strategy_candidate_type=candidate.strategy_candidate_type,
        r10_report_id=report.report_id,
        r10_policy=final_policy,
        manual_review_required=manual_review_required,
        reason_codes=reason_codes,
        source_report_type=report.report_type.value,
        source_analysis_scope=report.analysis.analysis_scope.value,
        source_macro_risk_level=report.analysis.macro_risk_level.value,
        source_sentiment=report.analysis.sentiment.value,
        normalized_catalyst_tags=normalized_catalyst_tags,
        generated_at=generated_at or datetime.now(UTC),
        notes=report.notes,
    )


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped
