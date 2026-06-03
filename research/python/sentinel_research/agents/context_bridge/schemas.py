from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_UNSAFE_TRADING_PATTERN = re.compile(
    r"\b(?:buy|sell|hold|entry|exit|trade)\b",
    re.IGNORECASE,
)


def _normalize_required_str(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _check_unsafe_trading_language(value: str, field_name: str) -> None:
    if _UNSAFE_TRADING_PATTERN.search(value):
        raise ValueError(f"{field_name} contains unsafe trading recommendation language")


class CandidateEvidenceTier(str, Enum):
    TIER_A = "Tier A"
    TIER_B = "Tier B"
    TIER_C = "Tier C"
    TIER_D = "Tier D"


class CandidateReviewStatus(str, Enum):
    MANUAL_REVIEW = "MANUAL_REVIEW"
    WATCHLIST_RESEARCH = "WATCHLIST_RESEARCH"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RequestedReviewType(str, Enum):
    R10_CONTEXT_RISK = "R10_CONTEXT_RISK"
    R11_FINANCIAL_STATEMENT = "R11_FINANCIAL_STATEMENT"
    CSE_DISCLOSURE = "CSE_DISCLOSURE"
    HUMAN_NOTES = "HUMAN_NOTES"


class CandidateTechnicalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_filtered_count: int = Field(..., ge=0)
    first_session: str | None = None
    last_session: str | None = None
    best_median_spread_percent: float | None = Field(default=None, ge=0.0)
    best_bid_ask_coverage_ratio: float | None = Field(default=None, ge=0.0)
    max_latest_turnover: float | None = Field(default=None, ge=0.0)

    @field_validator("first_session", "last_session", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)


class CandidateArtifactRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_root: str
    dossier_markdown_path: str | None = None
    session_stems: list[str] = Field(default_factory=list)

    @field_validator("runtime_root")
    @classmethod
    def _validate_runtime_root(cls, value: str) -> str:
        return _normalize_required_str(value, "runtime_root")

    @field_validator("dossier_markdown_path", mode="before")
    @classmethod
    def _normalize_optional_path(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("session_stems")
    @classmethod
    def _normalize_session_stems(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized.append(_normalize_required_str(item, "session_stems item"))
        return normalized


class CandidateSafetyFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_only: bool
    not_financial_advice: bool
    not_buy_sell_hold_recommendation: bool
    not_live_execution_guidance: bool
    human_review_required: bool

    @field_validator(
        "research_only",
        "not_financial_advice",
        "not_buy_sell_hold_recommendation",
        "not_live_execution_guidance",
        "human_review_required",
    )
    @classmethod
    def _require_true(cls, value: bool, info) -> bool:
        if value is not True:
            raise ValueError(f"{info.field_name} must be true")
        return value


class CandidateContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    request_id: None = None
    ticker: str
    company_name: str | None = None
    generated_from_dossier: bool
    evidence_tier: CandidateEvidenceTier
    review_status: CandidateReviewStatus
    sessions_seen: int = Field(..., ge=0)
    strong_full_grid_sessions: int = Field(..., ge=0)
    partial_coverage_sessions: int = Field(..., ge=0)
    baseline_count: int = Field(..., ge=0)
    diagnostic_count: int = Field(..., ge=0)
    variants_seen: list[str] = Field(default_factory=list)
    technical_summary: CandidateTechnicalSummary
    warnings: list[str] = Field(default_factory=list)
    requested_reviews: list[RequestedReviewType]
    artifact_refs: CandidateArtifactRefs
    safety: CandidateSafetyFlags

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "candidate-context-request/v0.1":
            raise ValueError(
                'schema_version must be "candidate-context-request/v0.1"'
            )
        return value

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return _normalize_required_str(value, "ticker").upper()

    @field_validator("company_name", mode="before")
    @classmethod
    def _normalize_company_name(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("generated_from_dossier")
    @classmethod
    def _require_generated_from_dossier(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("generated_from_dossier must be true")
        return value

    @field_validator("variants_seen")
    @classmethod
    def _normalize_variants_seen(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized.append(_normalize_required_str(item, "variants_seen item"))
        return normalized

    @field_validator("warnings")
    @classmethod
    def _validate_warnings(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized_item = _normalize_required_str(item, "warnings item")
            _check_unsafe_trading_language(normalized_item, "warnings")
            normalized.append(normalized_item)
        return normalized

    @field_validator("requested_reviews")
    @classmethod
    def _validate_requested_reviews(
        cls,
        value: list[RequestedReviewType],
    ) -> list[RequestedReviewType]:
        if not value:
            raise ValueError("requested_reviews must not be empty")
        return value
