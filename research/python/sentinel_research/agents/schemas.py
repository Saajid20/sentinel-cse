from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalysisScope(str, Enum):
    MARKET = "MARKET"
    SECTOR = "SECTOR"
    TICKER = "TICKER"


class MacroRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Sentiment(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class SignalPolicy(str, Enum):
    SUPPORT = "SUPPORT"
    BLOCK = "BLOCK"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_EFFECT = "NO_EFFECT"


class StalenessRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceType(str, Enum):
    CBSL = "CBSL"
    CSE_DISCLOSURE = "CSE_DISCLOSURE"
    NEWS = "NEWS"
    DAILY_FT = "DAILY_FT"
    OTHER = "OTHER"


_UNSAFE_PATTERN = re.compile(
    r"\b(?:buy|sell|strong\s+buy|strong\s+sell|hold|target\s+price|price\s+target|"
    r"take\s+profit|stop\s+loss|go\s+long|go\s+short|enter\s+trade|exit\s+trade|"
    r"place\s+order|execute\s+order|market\s+order|limit\s+order|accumulate|dump)\b",
    re.IGNORECASE,
)


def _check_unsafe_language(value: str, field_name: str) -> None:
    if _UNSAFE_PATTERN.search(value):
        raise ValueError(f"{field_name} contains unsafe trading recommendation language")


def _check_unsafe_language_in_list(values: list[str], field_name: str) -> None:
    for item in values:
        _check_unsafe_language(item, field_name)


class EvidenceSource(BaseModel):
    source_type: SourceType
    title: str = Field(..., min_length=1)
    url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime

    @field_validator("title")
    @classmethod
    def _title_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("EvidenceSource.title must not be empty")
        return stripped


class CseNewsAnalysis(BaseModel):
    schema_version: str
    analysis_scope: AnalysisScope
    ticker: str | None = None
    sector: str | None = None
    macro_risk_level: MacroRiskLevel
    sentiment: Sentiment
    catalyst_tags: list[str] = Field(default_factory=list)
    affected_tickers: list[str] = Field(default_factory=list)
    affected_sectors: list[str] = Field(default_factory=list)
    signal_policy: SignalPolicy
    manual_review_required: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    valid_until: datetime
    staleness_risk: StalenessRisk
    reason_codes: list[str] = Field(default_factory=list)
    short_summary: str = Field(..., min_length=1, max_length=700)
    sources: list[EvidenceSource] = Field(..., min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, v: str) -> str:
        if v != "r10_news_analyst_v1":
            raise ValueError(
                f'schema_version must be "r10_news_analyst_v1", got {v!r}'
            )
        return v

    @field_validator("ticker", "sector", mode="before")
    @classmethod
    def _strip_optional_str(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v

    @field_validator("catalyst_tags", "affected_tickers", "affected_sectors", "reason_codes")
    @classmethod
    def _strip_list_items(cls, v: list[str]) -> list[str]:
        return [item.strip() for item in v]

    @field_validator("short_summary")
    @classmethod
    def _validate_short_summary(cls, v: str) -> str:
        stripped = v.strip()
        _check_unsafe_language(stripped, "short_summary")
        return stripped

    @field_validator("reason_codes")
    @classmethod
    def _validate_reason_codes_unsafe(cls, v: list[str]) -> list[str]:
        _check_unsafe_language_in_list(v, "reason_codes")
        return v

    @model_validator(mode="after")
    def _validate_scope_requires_key(self) -> CseNewsAnalysis:
        if self.analysis_scope == AnalysisScope.TICKER and not self.ticker:
            raise ValueError("ticker is required when analysis_scope is TICKER")
        if self.analysis_scope == AnalysisScope.SECTOR and not self.sector:
            raise ValueError("sector is required when analysis_scope is SECTOR")
        return self
