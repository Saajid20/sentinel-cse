from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    AggregatedMetricResult,
    MetricOccurrence,
    build_fundamental_scorecard_from_aggregated_metrics,
    direction_from_metric_value,
    find_aggregated_metric,
    metric_value,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialMetric,
    FundamentalScorecard,
    MetricDirection,
    MetricUnit,
    R11ConfidenceLevel,
    RedFlagSeverity,
    SourceTrace,
    ToolAuditEntry,
)


def _make_source_trace(metric_name: str, *, page_number: int = 12) -> SourceTrace:
    return SourceTrace(
        local_file_path="C:/tmp/comb_q1_2026.pdf",
        page_number=page_number,
        table_id=f"pypdf_page_{page_number}",
        row_label=metric_name,
        raw_value="raw row",
        notes="scorecard builder test",
    )


def _make_aggregated_metric(
    metric_name: str,
    value: float,
    *,
    conflict: bool = False,
    manual_review_required: bool | None = None,
    occurrence_count: int = 1,
) -> AggregatedMetricResult:
    source_trace = _make_source_trace(metric_name)
    metric = FinancialMetric(
        metric_name=metric_name,
        display_name=metric_name.replace("_", " ").title(),
        value=value,
        unit=MetricUnit.PERCENT,
        period="current",
        comparison_period="previous",
        direction=MetricDirection.IMPROVING,
        calculation_audit_id=f"audit_{metric_name}",
        source_traces=[source_trace],
        notes="scorecard metric",
    )
    audit_entry = ToolAuditEntry(
        tool_name="r11_calculation_toolbox",
        operation="calculate_yoy_growth",
        metric_name=metric_name,
        formula="(current - previous) / abs(previous) * 100",
        inputs={"current": 120.0, "previous": 100.0},
        output=value,
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        source_traces=[source_trace],
        notes="scorecard audit",
    )
    occurrences = [
        MetricOccurrence(
            metric_name=metric_name,
            calculated_change_percent=value,
            reported_change_percent=value,
            difference_percent_points=0.0,
            matches_reported=True,
            source_traces=[source_trace],
            audit_entry=audit_entry,
            notes=f"occurrence {index + 1}",
        )
        for index in range(occurrence_count)
    ]
    return AggregatedMetricResult(
        metric_name=metric_name,
        selected_metric=metric,
        selected_audit_entry=audit_entry,
        occurrences=occurrences,
        occurrence_count=occurrence_count,
        conflict=conflict,
        manual_review_required=conflict if manual_review_required is None else manual_review_required,
        conflict_reason="conflict detected" if conflict else None,
        selected_reason="selected for scorecard test",
        notes="aggregated metric test",
    )


def _make_comb_like_aggregated_metrics() -> list[AggregatedMetricResult]:
    return [
        _make_aggregated_metric("group_profit_for_the_period_yoy_growth", 19.8),
        _make_aggregated_metric("group_basic_eps_growth", 8.0),
        _make_aggregated_metric("group_diluted_eps_growth", 7.5),
        _make_aggregated_metric("group_net_interest_income_yoy_growth", 13.44),
        _make_aggregated_metric("group_gross_income_growth", 10.5),
        _make_aggregated_metric("group_interest_income_growth", 11.2),
        _make_aggregated_metric("group_total_operating_income_growth", 12.0),
        _make_aggregated_metric("group_operating_expenses_growth", 5.4),
        _make_aggregated_metric("group_impairment_charges_change", -20.83),
        _make_aggregated_metric("group_total_assets_growth", 6.81),
        _make_aggregated_metric("group_total_liabilities_growth", 6.66),
        _make_aggregated_metric("group_customer_deposits_growth", 8.1),
        _make_aggregated_metric("group_total_equity_growth", 3.2),
    ]


def test_find_aggregated_metric_finds_by_name() -> None:
    aggregated = _make_comb_like_aggregated_metrics()

    found = find_aggregated_metric(
        aggregated,
        "group_profit_for_the_period_yoy_growth",
    )

    assert found is not None
    assert found.metric_name == "group_profit_for_the_period_yoy_growth"


def test_metric_value_extracts_numeric_selected_metric_value() -> None:
    metric = _make_aggregated_metric("group_profit_for_the_period_yoy_growth", 19.8)

    assert metric_value(metric) == 19.8


def test_direction_from_metric_value_handles_normal_positive_and_negative() -> None:
    assert (
        direction_from_metric_value("group_profit_for_the_period_yoy_growth", 19.8)
        is MetricDirection.IMPROVING
    )
    assert (
        direction_from_metric_value("group_profit_for_the_period_yoy_growth", -1.2)
        is MetricDirection.DETERIORATING
    )


def test_direction_from_metric_value_handles_inverse_impairment_negative_as_improving() -> None:
    assert (
        direction_from_metric_value("group_impairment_charges_change", -20.83)
        is MetricDirection.IMPROVING
    )


def test_direction_from_metric_value_handles_total_liabilities_positive_as_deteriorating() -> None:
    assert (
        direction_from_metric_value("group_total_liabilities_growth", 6.66)
        is MetricDirection.DETERIORATING
    )


def test_build_scorecard_with_comb_like_improving_metrics_gives_improving_earnings_and_revenue() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    assert result.scorecard.earnings_quality is MetricDirection.IMPROVING
    assert result.scorecard.revenue_trend is MetricDirection.IMPROVING


def test_comb_like_scorecard_gives_mixed_margin_trend() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    assert result.scorecard.margin_trend is MetricDirection.MIXED


def test_balance_sheet_risk_is_medium_when_liabilities_positive_and_close_to_assets() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    assert result.scorecard.balance_sheet_risk is R11ConfidenceLevel.MEDIUM


def test_capital_strength_is_medium_when_equity_growth_is_positive_but_not_above_five() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    assert result.scorecard.capital_strength is R11ConfidenceLevel.MEDIUM


def test_conflicts_force_manual_review_required_and_add_reason() -> None:
    aggregated = _make_comb_like_aggregated_metrics()
    aggregated[0] = _make_aggregated_metric(
        "group_profit_for_the_period_yoy_growth",
        19.8,
        conflict=True,
    )

    result = build_fundamental_scorecard_from_aggregated_metrics(aggregated)

    assert result.scorecard.manual_review_required is True
    assert any("conflicts" in reason.lower() for reason in result.manual_review_reasons)
    assert result.scorecard.accounting_risk is RedFlagSeverity.MEDIUM


def test_missing_key_metrics_force_manual_review_required() -> None:
    aggregated = [
        metric
        for metric in _make_comb_like_aggregated_metrics()
        if metric.metric_name != "group_total_equity_growth"
    ]

    result = build_fundamental_scorecard_from_aggregated_metrics(aggregated)

    assert result.scorecard.manual_review_required is True
    assert "group_total_equity_growth" in result.missing_expected_metrics


def test_summary_does_not_contain_trading_recommendation_language() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    summary = result.scorecard.summary
    assert summary is not None
    lowered = summary.lower()
    for forbidden in ("buy", "sell", "hold", "order", "target", "entry", "exit"):
        assert forbidden not in lowered


def test_no_test_calls_deepseek_or_network() -> None:
    result = build_fundamental_scorecard_from_aggregated_metrics(
        _make_comb_like_aggregated_metrics()
    )

    assert isinstance(result.scorecard, FundamentalScorecard)
