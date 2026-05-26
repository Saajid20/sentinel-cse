from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sentinel_research.agents.r11.analysis.metric_aggregator import (
    AggregatedMetricResult,
    has_metric_conflicts,
)
from sentinel_research.agents.r11.schemas import (
    FundamentalScorecard,
    MetricDirection,
    R11ConfidenceLevel,
    RedFlagSeverity,
)


class R11ScorecardBuildError(ValueError):
    """Raised when deterministic R11 scorecard construction fails."""


class ScorecardBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorecard: FundamentalScorecard
    metric_names_used: list[str]
    missing_expected_metrics: list[str] = []
    manual_review_reasons: list[str] = []
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @model_validator(mode="after")
    def _validate_review_consistency(self) -> ScorecardBuildResult:
        if self.manual_review_reasons:
            self.scorecard.manual_review_required = True
        return self


_INVERSE_DIRECTION_METRICS = {
    "group_impairment_charges_change",
    "group_operating_expenses_growth",
    "group_total_liabilities_growth",
}
_KEY_METRICS = [
    "group_profit_for_the_period_yoy_growth",
    "group_total_assets_growth",
    "group_total_liabilities_growth",
    "group_total_equity_growth",
]
_EARNINGS_METRICS = [
    "group_profit_for_the_period_yoy_growth",
    "group_basic_eps_growth",
    "group_diluted_eps_growth",
    "group_net_interest_income_yoy_growth",
]
_REVENUE_METRICS = [
    "group_gross_income_growth",
    "group_interest_income_growth",
    "group_total_operating_income_growth",
]


def find_aggregated_metric(
    aggregated: list[AggregatedMetricResult],
    metric_name: str,
) -> AggregatedMetricResult | None:
    for item in aggregated:
        if item.metric_name == metric_name:
            return item
    return None


def metric_value(aggregated_metric: AggregatedMetricResult | None) -> float | None:
    if aggregated_metric is None:
        return None
    value = aggregated_metric.selected_metric.value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def direction_from_metric_value(metric_name: str, value: float) -> MetricDirection:
    tolerance = 0.05
    if abs(value) <= tolerance:
        return MetricDirection.STABLE

    if metric_name in _INVERSE_DIRECTION_METRICS:
        return MetricDirection.DETERIORATING if value > 0 else MetricDirection.IMPROVING

    return MetricDirection.IMPROVING if value > 0 else MetricDirection.DETERIORATING


def build_fundamental_scorecard_from_aggregated_metrics(
    aggregated: list[AggregatedMetricResult],
) -> ScorecardBuildResult:
    metric_names_used: list[str] = []
    missing_expected_metrics: list[str] = []
    manual_review_reasons: list[str] = []

    for metric_name in _KEY_METRICS:
        if find_aggregated_metric(aggregated, metric_name) is None:
            missing_expected_metrics.append(metric_name)

    if missing_expected_metrics:
        manual_review_reasons.append(
            "Missing key aggregated metrics: "
            + ", ".join(missing_expected_metrics)
            + "."
        )

    if has_metric_conflicts(aggregated):
        conflict_metric_names = [
            item.metric_name for item in aggregated if item.conflict
        ]
        manual_review_reasons.append(
            "Aggregated metric conflicts detected: "
            + ", ".join(conflict_metric_names)
            + "."
        )

    earnings_quality = _majority_direction_from_metric_names(
        aggregated,
        _EARNINGS_METRICS,
        metric_names_used=metric_names_used,
    )
    if earnings_quality is MetricDirection.UNKNOWN:
        manual_review_reasons.append(
            "Earnings quality could not be determined from available aggregated metrics."
        )

    revenue_trend = _majority_direction_from_metric_names(
        aggregated,
        _REVENUE_METRICS,
        metric_names_used=metric_names_used,
    )

    margin_trend = _build_margin_trend(
        aggregated,
        metric_names_used=metric_names_used,
    )
    balance_sheet_risk = _build_balance_sheet_risk(
        aggregated,
        metric_names_used=metric_names_used,
    )
    capital_strength = _build_capital_strength(
        aggregated,
        metric_names_used=metric_names_used,
    )
    accounting_risk = (
        RedFlagSeverity.MEDIUM if has_metric_conflicts(aggregated) else None
    )

    scorecard = FundamentalScorecard(
        earnings_quality=earnings_quality,
        revenue_trend=revenue_trend,
        margin_trend=margin_trend,
        balance_sheet_risk=balance_sheet_risk,
        cash_flow_quality=MetricDirection.UNKNOWN,
        capital_strength=capital_strength,
        accounting_risk=accounting_risk,
        manual_review_required=bool(manual_review_reasons),
        summary=_build_summary(
            earnings_quality=earnings_quality,
            revenue_trend=revenue_trend,
            margin_trend=margin_trend,
        ),
    )

    return ScorecardBuildResult(
        scorecard=scorecard,
        metric_names_used=metric_names_used,
        missing_expected_metrics=missing_expected_metrics,
        manual_review_reasons=manual_review_reasons,
        notes="Deterministic scorecard prototype built from aggregated verified metrics.",
    )


def _append_metric_name(metric_names_used: list[str], metric_name: str) -> None:
    if metric_name not in metric_names_used:
        metric_names_used.append(metric_name)


def _majority_direction_from_metric_names(
    aggregated: list[AggregatedMetricResult],
    metric_names: list[str],
    *,
    metric_names_used: list[str],
) -> MetricDirection:
    directions: list[MetricDirection] = []
    for metric_name in metric_names:
        aggregated_metric = find_aggregated_metric(aggregated, metric_name)
        value = metric_value(aggregated_metric)
        if value is None:
            continue
        _append_metric_name(metric_names_used, metric_name)
        directions.append(direction_from_metric_value(metric_name, value))

    if not directions:
        return MetricDirection.UNKNOWN

    counts = {
        MetricDirection.IMPROVING: directions.count(MetricDirection.IMPROVING),
        MetricDirection.DETERIORATING: directions.count(MetricDirection.DETERIORATING),
        MetricDirection.STABLE: directions.count(MetricDirection.STABLE),
    }
    highest_count = max(counts.values())
    highest_directions = [
        direction for direction, count in counts.items() if count == highest_count
    ]
    if len(highest_directions) == 1:
        return highest_directions[0]
    return MetricDirection.MIXED


def _build_margin_trend(
    aggregated: list[AggregatedMetricResult],
    *,
    metric_names_used: list[str],
) -> MetricDirection:
    impairment_name = "group_impairment_charges_change"
    expenses_name = "group_operating_expenses_growth"
    impairment_metric = find_aggregated_metric(aggregated, impairment_name)
    expenses_metric = find_aggregated_metric(aggregated, expenses_name)
    impairment_value = metric_value(impairment_metric)
    expenses_value = metric_value(expenses_metric)

    impairment_direction = None
    if impairment_value is not None:
        _append_metric_name(metric_names_used, impairment_name)
        impairment_direction = direction_from_metric_value(
            impairment_name,
            impairment_value,
        )

    expenses_direction = None
    if expenses_value is not None:
        _append_metric_name(metric_names_used, expenses_name)
        expenses_direction = direction_from_metric_value(
            expenses_name,
            expenses_value,
        )

    if impairment_direction is None and expenses_direction is None:
        return MetricDirection.UNKNOWN
    if impairment_direction is None:
        return expenses_direction or MetricDirection.UNKNOWN
    if expenses_direction is None:
        return impairment_direction
    if impairment_direction is expenses_direction:
        return impairment_direction
    return MetricDirection.MIXED


def _build_balance_sheet_risk(
    aggregated: list[AggregatedMetricResult],
    *,
    metric_names_used: list[str],
) -> R11ConfidenceLevel | None:
    assets_name = "group_total_assets_growth"
    liabilities_name = "group_total_liabilities_growth"
    deposits_name = "group_customer_deposits_growth"
    assets_metric = find_aggregated_metric(aggregated, assets_name)
    liabilities_metric = find_aggregated_metric(aggregated, liabilities_name)
    deposits_metric = find_aggregated_metric(aggregated, deposits_name)
    assets_growth = metric_value(assets_metric)
    liabilities_growth = metric_value(liabilities_metric)
    deposits_growth = metric_value(deposits_metric)

    if assets_growth is not None:
        _append_metric_name(metric_names_used, assets_name)
    if liabilities_growth is not None:
        _append_metric_name(metric_names_used, liabilities_name)
    if deposits_growth is not None:
        _append_metric_name(metric_names_used, deposits_name)

    if assets_growth is None or liabilities_growth is None:
        return None

    growth_gap = liabilities_growth - assets_growth
    if liabilities_growth < 0:
        return R11ConfidenceLevel.LOW
    if growth_gap > 2.0:
        return R11ConfidenceLevel.HIGH
    if growth_gap < -2.0:
        return R11ConfidenceLevel.LOW
    return R11ConfidenceLevel.MEDIUM


def _build_capital_strength(
    aggregated: list[AggregatedMetricResult],
    *,
    metric_names_used: list[str],
) -> R11ConfidenceLevel | None:
    equity_name = "group_total_equity_growth"
    equity_metric = find_aggregated_metric(aggregated, equity_name)
    equity_growth = metric_value(equity_metric)
    if equity_growth is None:
        return None

    _append_metric_name(metric_names_used, equity_name)
    if equity_growth > 5.0:
        return R11ConfidenceLevel.HIGH
    if equity_growth >= 0.0:
        return R11ConfidenceLevel.MEDIUM
    return R11ConfidenceLevel.LOW


def _build_summary(
    *,
    earnings_quality: MetricDirection,
    revenue_trend: MetricDirection,
    margin_trend: MetricDirection,
) -> str:
    summary_parts = [
        "Deterministic R11 scorecard built from verified financial statement metrics."
    ]
    if earnings_quality is MetricDirection.IMPROVING and revenue_trend is MetricDirection.IMPROVING:
        summary_parts.append("Earnings and revenue trends improved.")
    elif earnings_quality is MetricDirection.DETERIORATING or revenue_trend is MetricDirection.DETERIORATING:
        summary_parts.append("Earnings or revenue trends weakened.")
    else:
        summary_parts.append("Earnings and revenue trends were mixed or incomplete.")

    if margin_trend is MetricDirection.DETERIORATING:
        summary_parts.append("Operating cost pressure remains a conservative watch item.")
    elif margin_trend is MetricDirection.MIXED:
        summary_parts.append("Margin signals were mixed across operating expenses and impairment trends.")
    elif margin_trend is MetricDirection.IMPROVING:
        summary_parts.append("Margin-related signals improved in the available prototype metrics.")

    return " ".join(summary_parts)


__all__ = [
    "R11ScorecardBuildError",
    "ScorecardBuildResult",
    "find_aggregated_metric",
    "metric_value",
    "direction_from_metric_value",
    "build_fundamental_scorecard_from_aggregated_metrics",
]
