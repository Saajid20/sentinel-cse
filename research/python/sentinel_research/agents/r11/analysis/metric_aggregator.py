from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sentinel_research.agents.r11.analysis.metric_builder import MetricVerificationResult
from sentinel_research.agents.r11.schemas import FinancialMetric, SourceTrace, ToolAuditEntry


class R11MetricAggregationError(ValueError):
    """Raised when deterministic R11 metric aggregation fails."""


class MetricOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    calculated_change_percent: float
    reported_change_percent: float | None = None
    difference_percent_points: float | None = None
    matches_reported: bool | None = None
    source_traces: list[SourceTrace] = []
    audit_entry: ToolAuditEntry | None = None
    notes: str | None = None

    @field_validator("metric_name")
    @classmethod
    def _validate_metric_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("metric_name must not be empty")
        return normalized

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class AggregatedMetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    selected_metric: FinancialMetric
    selected_audit_entry: ToolAuditEntry
    occurrences: list[MetricOccurrence]
    occurrence_count: int
    conflict: bool = False
    manual_review_required: bool = False
    conflict_reason: str | None = None
    selected_reason: str | None = None
    notes: str | None = None

    @field_validator("metric_name")
    @classmethod
    def _validate_metric_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("metric_name must not be empty")
        return normalized

    @field_validator("occurrences")
    @classmethod
    def _validate_occurrences(cls, value: list[MetricOccurrence]) -> list[MetricOccurrence]:
        if not value:
            raise ValueError("occurrences must not be empty")
        return value

    @field_validator("conflict_reason", "selected_reason", "notes", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @model_validator(mode="after")
    def _validate_consistency(self) -> AggregatedMetricResult:
        self.occurrence_count = len(self.occurrences)
        if self.selected_metric.metric_name != self.metric_name:
            raise ValueError("selected_metric.metric_name must match metric_name")
        if self.selected_audit_entry.metric_name != self.metric_name:
            raise ValueError("selected_audit_entry.metric_name must match metric_name")
        for occurrence in self.occurrences:
            if occurrence.metric_name != self.metric_name:
                raise ValueError("occurrence.metric_name must match metric_name")
        if self.conflict:
            self.manual_review_required = True
        return self


def metric_occurrence_from_result(result: MetricVerificationResult) -> MetricOccurrence:
    return MetricOccurrence(
        metric_name=result.metric.metric_name,
        calculated_change_percent=result.calculated_change_percent,
        reported_change_percent=result.reported_change_percent,
        difference_percent_points=result.difference_percent_points,
        matches_reported=result.matches_reported,
        source_traces=[trace.model_copy(deep=True) for trace in result.metric.source_traces],
        audit_entry=result.audit_entry.model_copy(deep=True),
        notes=result.notes or result.metric.notes or result.audit_entry.notes,
    )


def _values_close(a: float | None, b: float | None, tolerance: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance


def aggregate_metric_results(
    results: list[MetricVerificationResult],
    *,
    value_tolerance_percent_points: float = 0.05,
) -> list[AggregatedMetricResult]:
    if value_tolerance_percent_points < 0:
        raise R11MetricAggregationError("value_tolerance_percent_points must be >= 0")

    grouped_results: dict[str, list[MetricVerificationResult]] = {}
    metric_order: list[str] = []
    for result in results:
        metric_name = result.metric.metric_name
        if metric_name not in grouped_results:
            grouped_results[metric_name] = []
            metric_order.append(metric_name)
        grouped_results[metric_name].append(result)

    aggregated_results: list[AggregatedMetricResult] = []
    for metric_name in metric_order:
        grouped = grouped_results[metric_name]
        occurrences = [metric_occurrence_from_result(result) for result in grouped]
        selected_index = _select_preferred_result_index(grouped)
        selected_result = grouped[selected_index]
        conflict, conflict_reason = _detect_group_conflict(
            grouped,
            tolerance=value_tolerance_percent_points,
        )

        aggregated_results.append(
            AggregatedMetricResult(
                metric_name=metric_name,
                selected_metric=selected_result.metric.model_copy(deep=True),
                selected_audit_entry=selected_result.audit_entry.model_copy(deep=True),
                occurrences=occurrences,
                occurrence_count=len(occurrences),
                conflict=conflict,
                manual_review_required=conflict,
                conflict_reason=conflict_reason,
                selected_reason=_build_selected_reason(selected_result),
                notes=_build_aggregation_notes(
                    occurrence_count=len(occurrences),
                    conflict=conflict,
                    conflict_reason=conflict_reason,
                ),
            )
        )

    return aggregated_results


def split_aggregated_metrics(
    aggregated: list[AggregatedMetricResult],
) -> tuple[list[FinancialMetric], list[ToolAuditEntry]]:
    metric_names: set[str] = set()
    metrics: list[FinancialMetric] = []
    audit_entries: list[ToolAuditEntry] = []

    for item in aggregated:
        if item.metric_name in metric_names:
            raise R11MetricAggregationError(
                f"duplicate aggregated metric name: {item.metric_name}"
            )
        metric_names.add(item.metric_name)
        metrics.append(item.selected_metric)
        audit_entries.append(item.selected_audit_entry)

    return metrics, audit_entries


def has_metric_conflicts(aggregated: list[AggregatedMetricResult]) -> bool:
    return any(item.conflict for item in aggregated)


def _select_preferred_result_index(results: list[MetricVerificationResult]) -> int:
    if not results:
        raise R11MetricAggregationError("cannot select from empty metric result group")

    ranked_indices = sorted(
        range(len(results)),
        key=lambda index: (
            _matches_rank(results[index].matches_reported),
            0 if results[index].reported_change_percent is not None else 1,
            -len(results[index].metric.source_traces),
            index,
        ),
    )
    return ranked_indices[0]


def _matches_rank(value: bool | None) -> int:
    if value is True:
        return 0
    if value is None:
        return 1
    return 2


def _detect_group_conflict(
    results: list[MetricVerificationResult],
    *,
    tolerance: float,
) -> tuple[bool, str | None]:
    if not results:
        raise R11MetricAggregationError("cannot aggregate empty metric result group")

    reasons: list[str] = []
    baseline = results[0]

    for other in results[1:]:
        if not _values_close(
            baseline.calculated_change_percent,
            other.calculated_change_percent,
            tolerance,
        ):
            reasons.append("calculated change percentages differ beyond tolerance")
            break

    for other in results[1:]:
        if not _values_close(
            baseline.reported_change_percent,
            other.reported_change_percent,
            tolerance,
        ):
            reasons.append("reported change percentages differ beyond tolerance")
            break

    match_values = {result.matches_reported for result in results}
    if False in match_values and (True in match_values or None in match_values):
        reasons.append("reported match status disagrees across duplicate metrics")

    if not reasons:
        return False, None
    return True, "; ".join(reasons)


def _build_selected_reason(result: MetricVerificationResult) -> str:
    if result.matches_reported is True:
        return "Selected preferred occurrence with reported-match verification."
    if result.reported_change_percent is not None:
        return "Selected preferred occurrence with reported change percentage."
    if result.metric.source_traces:
        return "Selected preferred occurrence with richer source trace coverage."
    return "Selected first occurrence deterministically."


def _build_aggregation_notes(
    *,
    occurrence_count: int,
    conflict: bool,
    conflict_reason: str | None,
) -> str:
    if conflict and conflict_reason is not None:
        return (
            f"Aggregated {occurrence_count} duplicate occurrences with conflict: "
            f"{conflict_reason}."
        )
    return f"Aggregated {occurrence_count} duplicate occurrences without conflict."


__all__ = [
    "R11MetricAggregationError",
    "MetricOccurrence",
    "AggregatedMetricResult",
    "metric_occurrence_from_result",
    "aggregate_metric_results",
    "split_aggregated_metrics",
    "has_metric_conflicts",
]
