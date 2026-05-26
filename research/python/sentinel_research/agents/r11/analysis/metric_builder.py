from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.schemas import (
    FinancialMetric,
    MetricDirection,
    MetricUnit,
    SourceTrace,
    ToolAuditEntry,
)
from sentinel_research.agents.r11.tables.value_mapper import (
    MappedLineItemValues,
    ParsedFinancialValue,
    get_required_numeric,
)
from sentinel_research.agents.r11.tools.calculations import (
    R11CalculationError,
    calculate_yoy_growth,
    round_metric,
)


class R11MetricBuildError(ValueError):
    """Raised when deterministic R11 metric generation fails."""


VERIFIED_GROWTH_METRIC_MAP: dict[str, str] = {
    "net_interest_income": "net_interest_income_yoy_growth",
    "impairment_charges_and_other_losses": "impairment_charges_change",
    "profit_for_the_period": "profit_for_the_period_yoy_growth",
    "total_assets": "total_assets_growth",
    "customer_deposits": "customer_deposits_growth",
    "total_liabilities": "total_liabilities_growth",
    "total_equity": "total_equity_growth",
    "gross_income": "gross_income_growth",
    "interest_income": "interest_income_growth",
    "total_operating_income": "total_operating_income_growth",
    "operating_expenses": "operating_expenses_growth",
    "basic_eps": "basic_eps_growth",
    "diluted_eps": "diluted_eps_growth",
    "net_asset_value_per_share": "net_asset_value_per_share_growth",
}

_SUPPORTED_ENTITY_PREFIXES = {"group", "bank"}
_INVERSE_DIRECTION_METRICS = {
    "impairment_charges_change",
    "operating_expenses_growth",
    "interest_expense_growth",
    "total_liabilities_growth",
}


class MetricVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: FinancialMetric
    audit_entry: ToolAuditEntry
    reported_change_percent: float | None = None
    calculated_change_percent: float
    difference_percent_points: float | None = None
    matches_reported: bool | None = None
    tolerance_percent_points: float = 0.05
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


def determine_growth_direction(
    metric_name: str,
    calculated_change_percent: float,
    *,
    tolerance_percent: float = 0.05,
) -> MetricDirection:
    if tolerance_percent < 0:
        raise R11MetricBuildError("tolerance_percent must be >= 0")

    normalized_metric_name = metric_name.strip().lower()
    if not normalized_metric_name:
        return MetricDirection.UNKNOWN

    absolute_change = abs(calculated_change_percent)
    if absolute_change <= tolerance_percent:
        return MetricDirection.STABLE

    is_positive = calculated_change_percent > 0
    if normalized_metric_name in _INVERSE_DIRECTION_METRICS:
        return MetricDirection.DETERIORATING if is_positive else MetricDirection.IMPROVING

    return MetricDirection.IMPROVING if is_positive else MetricDirection.DETERIORATING


def build_growth_metric_for_item(
    item: MappedLineItemValues,
    *,
    entity_prefix: str = "group",
    tolerance_percent_points: float = 0.05,
    generated_at: datetime | None = None,
) -> MetricVerificationResult | None:
    metric_suffix = VERIFIED_GROWTH_METRIC_MAP.get(item.canonical_name)
    if metric_suffix is None:
        return None

    if entity_prefix not in _SUPPORTED_ENTITY_PREFIXES:
        raise R11MetricBuildError("entity_prefix must be 'group' or 'bank'")

    if tolerance_percent_points < 0:
        raise R11MetricBuildError("tolerance_percent_points must be >= 0")

    current_key = f"{entity_prefix}_current"
    previous_key = f"{entity_prefix}_previous"
    reported_key = f"{entity_prefix}_reported_change_percent"
    metric_name = f"{entity_prefix}_{metric_suffix}"
    source_traces = _collect_source_traces(item.source_trace)
    generated_timestamp = _normalize_generated_at(generated_at)

    try:
        current_value = get_required_numeric(item, current_key)
        previous_value = get_required_numeric(item, previous_key)
        calculated_change_percent = round_metric(
            calculate_yoy_growth(current_value, previous_value) * 100.0,
            2,
        )
    except (R11CalculationError, ValueError) as exc:
        raise R11MetricBuildError(
            f"failed to build metric for {item.canonical_name}: {exc}"
        ) from exc

    reported_change_percent = _get_optional_numeric(item.mapped_values.get(reported_key))
    difference_percent_points: float | None = None
    matches_reported: bool | None = None

    if reported_change_percent is not None:
        difference_percent_points = round_metric(
            calculated_change_percent - reported_change_percent,
            2,
        )
        matches_reported = abs(difference_percent_points) <= tolerance_percent_points

    metric_notes = _build_metric_notes(
        reported_change_percent=reported_change_percent,
        matches_reported=matches_reported,
        tolerance_percent_points=tolerance_percent_points,
    )

    metric = FinancialMetric(
        metric_name=metric_name,
        display_name=_build_display_name(entity_prefix, item.original_label),
        value=calculated_change_percent,
        unit=MetricUnit.PERCENT,
        period="current",
        comparison_period="previous",
        direction=determine_growth_direction(
            metric_suffix,
            calculated_change_percent,
            tolerance_percent=tolerance_percent_points,
        ),
        calculation_audit_id=f"audit_{entity_prefix}_{metric_suffix}",
        source_traces=source_traces,
        notes=metric_notes,
    )

    audit_entry = ToolAuditEntry(
        tool_name="r11_calculation_toolbox",
        operation="calculate_yoy_growth",
        metric_name=metric.metric_name,
        formula="(current - previous) / abs(previous) * 100",
        inputs=_build_audit_inputs(
            current=current_value,
            previous=previous_value,
            reported_change_percent=reported_change_percent,
        ),
        output=calculated_change_percent,
        generated_at=generated_timestamp,
        source_traces=source_traces,
        notes=metric_notes,
    )

    return MetricVerificationResult(
        metric=metric,
        audit_entry=audit_entry,
        reported_change_percent=reported_change_percent,
        calculated_change_percent=calculated_change_percent,
        difference_percent_points=difference_percent_points,
        matches_reported=matches_reported,
        tolerance_percent_points=tolerance_percent_points,
        notes=metric_notes,
    )


def build_growth_metrics_for_items(
    items: list[MappedLineItemValues],
    *,
    entity_prefix: str = "group",
    tolerance_percent_points: float = 0.05,
    generated_at: datetime | None = None,
) -> list[MetricVerificationResult]:
    results: list[MetricVerificationResult] = []
    for item in items:
        result = build_growth_metric_for_item(
            item,
            entity_prefix=entity_prefix,
            tolerance_percent_points=tolerance_percent_points,
            generated_at=generated_at,
        )
        if result is None:
            continue
        results.append(result)
    return results


def split_metric_results(
    results: list[MetricVerificationResult],
) -> tuple[list[FinancialMetric], list[ToolAuditEntry]]:
    metrics = [result.metric for result in results]
    audit_entries = [result.audit_entry for result in results]
    return metrics, audit_entries


def _normalize_generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise R11MetricBuildError("generated_at must be timezone-aware")
    return value


def _collect_source_traces(source_trace: SourceTrace | None) -> list[SourceTrace]:
    return [source_trace] if source_trace is not None else []


def _get_optional_numeric(parsed_value: ParsedFinancialValue | None) -> float | None:
    if parsed_value is None or parsed_value.value is None:
        return None
    return parsed_value.value


def _build_display_name(entity_prefix: str, original_label: str) -> str:
    return f"{entity_prefix.title()} {original_label.strip()} YoY Growth"


def _build_audit_inputs(
    *,
    current: float,
    previous: float,
    reported_change_percent: float | None,
) -> dict[str, int | float | str | None]:
    inputs: dict[str, int | float | str | None] = {
        "current": current,
        "previous": previous,
    }
    if reported_change_percent is not None:
        inputs["reported_change_percent"] = reported_change_percent
    return inputs


def _build_metric_notes(
    *,
    reported_change_percent: float | None,
    matches_reported: bool | None,
    tolerance_percent_points: float,
) -> str:
    if reported_change_percent is None:
        return "No reported change percentage was available for verification."
    if matches_reported:
        return (
            "Reported change matched calculated change within "
            f"{tolerance_percent_points:.2f} percentage points."
        )
    return (
        "Reported change did not match calculated change within "
        f"{tolerance_percent_points:.2f} percentage points."
    )


__all__ = [
    "R11MetricBuildError",
    "VERIFIED_GROWTH_METRIC_MAP",
    "MetricVerificationResult",
    "determine_growth_direction",
    "build_growth_metric_for_item",
    "build_growth_metrics_for_items",
    "split_metric_results",
]
