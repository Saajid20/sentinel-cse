from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.analysis.metric_aggregator import AggregatedMetricResult
from sentinel_research.agents.r11.analysis.scorecard_builder import ScorecardBuildResult
from sentinel_research.agents.r11.schemas import (
    AccountingRedFlag,
    FinancialMetric,
    R11AnalystDossier,
    R11ConfidenceLevel,
    R11DocumentType,
    SourceTrace,
    ToolAuditEntry,
    build_dossier_id,
)


class R11DossierBuildError(ValueError):
    """Raised when deterministic R11 dossier assembly fails."""


class DeterministicDossierBuildInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    analysis_title: str | None = None
    source_document_title: str | None = None
    source_document_url: str | None = None
    scorecard_result: ScorecardBuildResult
    aggregated_metrics: list[AggregatedMetricResult]
    financial_metrics: list[FinancialMetric]
    tool_audit_entries: list[ToolAuditEntry]
    source_traces: list[SourceTrace] = []
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be empty")
        return normalized

    @field_validator(
        "company_name",
        "analysis_title",
        "source_document_title",
        "source_document_url",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @field_validator("financial_metrics")
    @classmethod
    def _validate_financial_metrics(cls, value: list[FinancialMetric]) -> list[FinancialMetric]:
        if not value:
            raise ValueError("financial_metrics must not be empty")
        return value

    @field_validator("tool_audit_entries")
    @classmethod
    def _validate_tool_audit_entries(cls, value: list[ToolAuditEntry]) -> list[ToolAuditEntry]:
        if not value:
            raise ValueError("tool_audit_entries must not be empty")
        return value


def collect_source_traces_from_metrics(metrics: list[FinancialMetric]) -> list[SourceTrace]:
    traces: list[SourceTrace] = []
    seen_keys: set[str] = set()
    for metric in metrics:
        for source_trace in metric.source_traces:
            trace_copy = source_trace.model_copy(deep=True)
            trace_key = trace_copy.model_dump_json()
            if trace_key in seen_keys:
                continue
            seen_keys.add(trace_key)
            traces.append(trace_copy)
    return traces


def collect_red_flags_from_scorecard(
    scorecard_result: ScorecardBuildResult,
) -> list[AccountingRedFlag]:
    red_flags: list[AccountingRedFlag] = []
    if scorecard_result.scorecard.manual_review_required and scorecard_result.manual_review_reasons:
        description = "Deterministic scorecard requires manual review: " + "; ".join(
            scorecard_result.manual_review_reasons
        )
        red_flags.append(
            AccountingRedFlag(
                red_flag_id="r11_scorecard_manual_review",
                category="deterministic_scorecard_review",
                severity="MEDIUM",
                description=description,
                source_traces=[],
            )
        )

    if scorecard_result.missing_expected_metrics:
        description = "Expected deterministic scorecard metrics were missing: " + ", ".join(
            scorecard_result.missing_expected_metrics
        )
        red_flags.append(
            AccountingRedFlag(
                red_flag_id="r11_scorecard_missing_metrics",
                category="missing_deterministic_metrics",
                severity="LOW",
                description=description,
                source_traces=[],
            )
        )

    return red_flags


def build_deterministic_r11_dossier(
    build_input: DeterministicDossierBuildInput,
    *,
    generated_at: datetime | None = None,
) -> R11AnalystDossier:
    generated_timestamp = _normalize_generated_at(generated_at)
    metric_source_traces = collect_source_traces_from_metrics(build_input.financial_metrics)
    source_traces = _merge_source_traces(build_input.source_traces, metric_source_traces)
    if not source_traces:
        raise R11DossierBuildError("at least one source trace is required to build a dossier")

    company_name = _resolve_company_name(build_input, source_traces)
    red_flags = collect_red_flags_from_scorecard(build_input.scorecard_result)
    manual_review_required = (
        build_input.scorecard_result.scorecard.manual_review_required
        or bool(build_input.scorecard_result.manual_review_reasons)
        or bool(red_flags)
        or any(item.conflict for item in build_input.aggregated_metrics)
    )
    confidence = (
        R11ConfidenceLevel.HIGH
        if build_input.financial_metrics and not manual_review_required
        else R11ConfidenceLevel.MEDIUM
    )

    dossier_notes = _build_dossier_notes(build_input)

    return R11AnalystDossier(
        dossier_id=build_dossier_id(build_input.ticker, generated_timestamp),
        generated_at=generated_timestamp,
        ticker=build_input.ticker,
        company=company_name,
        document_type=R11DocumentType.CORPORATE_DISCLOSURE,
        source_traces=source_traces,
        extracted_tables=[],
        normalized_statements=[],
        financial_metrics=[metric.model_copy(deep=True) for metric in build_input.financial_metrics],
        fundamental_scorecard=build_input.scorecard_result.scorecard.model_copy(deep=True),
        accounting_red_flags=red_flags,
        tool_audit=[entry.model_copy(deep=True) for entry in build_input.tool_audit_entries],
        analyst_summary=build_input.scorecard_result.scorecard.summary,
        confidence=confidence,
        manual_review_required=manual_review_required,
        notes=dossier_notes,
    )


def _normalize_generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise R11DossierBuildError("generated_at must be timezone-aware")
    return value


def _merge_source_traces(
    explicit_source_traces: list[SourceTrace],
    metric_source_traces: list[SourceTrace],
) -> list[SourceTrace]:
    merged: list[SourceTrace] = []
    seen_keys: set[str] = set()
    for source_trace in [*explicit_source_traces, *metric_source_traces]:
        trace_copy = source_trace.model_copy(deep=True)
        trace_key = trace_copy.model_dump_json()
        if trace_key in seen_keys:
            continue
        seen_keys.add(trace_key)
        merged.append(trace_copy)
    return merged


def _resolve_company_name(
    build_input: DeterministicDossierBuildInput,
    source_traces: list[SourceTrace],
) -> str:
    if build_input.company_name:
        return build_input.company_name
    for source_trace in source_traces:
        if source_trace.company:
            return source_trace.company
    return build_input.ticker


def _build_dossier_notes(build_input: DeterministicDossierBuildInput) -> str | None:
    note_parts: list[str] = []
    if build_input.analysis_title:
        note_parts.append(f"analysis_title={build_input.analysis_title}")
    if build_input.source_document_title:
        note_parts.append(f"source_document_title={build_input.source_document_title}")
    if build_input.source_document_url:
        note_parts.append(f"source_document_url={build_input.source_document_url}")
    if build_input.notes:
        note_parts.append(build_input.notes)
    if not note_parts:
        return None
    return " | ".join(note_parts)


__all__ = [
    "R11DossierBuildError",
    "DeterministicDossierBuildInput",
    "collect_source_traces_from_metrics",
    "collect_red_flags_from_scorecard",
    "build_deterministic_r11_dossier",
]
