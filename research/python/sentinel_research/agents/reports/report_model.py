from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sentinel_research.agents.schemas import CseNewsAnalysis

_SAFE_SCOPE_KEY_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class ReportType(str, Enum):
    MARKET_CONTEXT = "MARKET_CONTEXT"
    SECTOR_CONTEXT = "SECTOR_CONTEXT"
    TICKER_CONTEXT = "TICKER_CONTEXT"
    SOURCE_DOCUMENT_CONTEXT = "SOURCE_DOCUMENT_CONTEXT"


class R10AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "r10_analysis_report_v1"
    report_id: str
    report_type: ReportType
    generated_at: datetime
    query: dict[str, object]
    analysis: CseNewsAnalysis
    source_document_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "r10_analysis_report_v1":
            raise ValueError(
                f'schema_version must be "r10_analysis_report_v1", got {value!r}'
            )
        return value

    @field_validator("report_id")
    @classmethod
    def _validate_report_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("report_id must not be empty")
        return normalized

    @field_validator("generated_at")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: dict[str, object]) -> dict[str, object]:
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("source_document_ids")
    @classmethod
    def _normalize_source_document_ids(cls, value: list[str]) -> list[str]:
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


def build_report_id(
    report_type: ReportType,
    generated_at: datetime,
    scope_key: str | None = None,
) -> str:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")

    timestamp = generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_id = f"r10_{report_type.value.lower()}_{timestamp}"

    if scope_key is None:
        return report_id

    normalized_scope_key = _SAFE_SCOPE_KEY_PATTERN.sub("_", scope_key.strip()).strip("_")
    if not normalized_scope_key:
        return report_id

    return f"{report_id}_{normalized_scope_key}"
