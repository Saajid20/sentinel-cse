from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    aggregate_metric_results,
    has_metric_conflicts,
    metric_occurrence_from_result,
    split_aggregated_metrics,
)
from sentinel_research.agents.r11.analysis.metric_builder import (  # noqa: E402
    MetricVerificationResult,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialMetric,
    MetricDirection,
    MetricUnit,
    SourceTrace,
    ToolAuditEntry,
)


def _make_source_trace(row_label: str, *, page_number: int = 12) -> SourceTrace:
    return SourceTrace(
        local_file_path="C:/tmp/comb_q1_2026.pdf",
        page_number=page_number,
        table_id=f"pypdf_page_{page_number}",
        row_label=row_label,
        raw_value="raw row",
        notes="metric aggregator test",
    )


def _make_result(
    metric_name: str,
    *,
    calculated_change_percent: float,
    reported_change_percent: float | None = None,
    difference_percent_points: float | None = None,
    matches_reported: bool | None = None,
    source_trace_count: int = 1,
    note_suffix: str = "metric aggregator test",
) -> MetricVerificationResult:
    source_traces = [
        _make_source_trace(f"{metric_name} row {index + 1}", page_number=12 + index)
        for index in range(source_trace_count)
    ]
    metric = FinancialMetric(
        metric_name=metric_name,
        display_name=metric_name.replace("_", " ").title(),
        value=calculated_change_percent,
        unit=MetricUnit.PERCENT,
        period="current",
        comparison_period="previous",
        direction=MetricDirection.IMPROVING,
        calculation_audit_id=f"audit_{metric_name}",
        source_traces=source_traces,
        notes=f"{note_suffix} metric",
    )
    audit_entry = ToolAuditEntry(
        tool_name="r11_calculation_toolbox",
        operation="calculate_yoy_growth",
        metric_name=metric_name,
        formula="(current - previous) / abs(previous) * 100",
        inputs={"current": 120.0, "previous": 100.0},
        output=calculated_change_percent,
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        source_traces=source_traces,
        notes=f"{note_suffix} audit",
    )
    return MetricVerificationResult(
        metric=metric,
        audit_entry=audit_entry,
        reported_change_percent=reported_change_percent,
        calculated_change_percent=calculated_change_percent,
        difference_percent_points=difference_percent_points,
        matches_reported=matches_reported,
        tolerance_percent_points=0.05,
        notes=f"{note_suffix} result",
    )


def test_metric_occurrence_from_result_preserves_core_fields() -> None:
    result = _make_result(
        "group_profit_for_the_period_yoy_growth",
        calculated_change_percent=19.8,
        reported_change_percent=19.8,
        difference_percent_points=0.0,
        matches_reported=True,
    )

    occurrence = metric_occurrence_from_result(result)

    assert occurrence.metric_name == "group_profit_for_the_period_yoy_growth"
    assert occurrence.calculated_change_percent == 19.8
    assert occurrence.reported_change_percent == 19.8
    assert occurrence.matches_reported is True
    assert len(occurrence.source_traces) == 1
    assert occurrence.audit_entry is not None
    assert occurrence.audit_entry.metric_name == "group_profit_for_the_period_yoy_growth"


def test_aggregate_metric_results_returns_one_result_for_one_metric() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            )
        ]
    )

    assert len(aggregated) == 1
    assert aggregated[0].occurrence_count == 1
    assert aggregated[0].conflict is False


def test_duplicate_identical_metrics_aggregate_without_conflict() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
        ]
    )

    assert len(aggregated) == 1
    assert aggregated[0].occurrence_count == 2
    assert aggregated[0].conflict is False


def test_duplicate_identical_metrics_preserve_both_occurrences() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
                source_trace_count=1,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
                source_trace_count=2,
            ),
        ]
    )

    assert len(aggregated[0].occurrences) == 2
    assert len(aggregated[0].occurrences[0].source_traces) == 1
    assert len(aggregated[0].occurrences[1].source_traces) == 2


def test_different_calculated_values_beyond_tolerance_set_conflict_and_manual_review() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=20.2,
                reported_change_percent=20.2,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
        ]
    )

    assert aggregated[0].conflict is True
    assert aggregated[0].manual_review_required is True


def test_different_reported_values_beyond_tolerance_set_conflict() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=20.2,
                difference_percent_points=-0.4,
                matches_reported=False,
            ),
        ]
    )

    assert aggregated[0].conflict is True
    assert aggregated[0].conflict_reason is not None


def test_matches_reported_false_causes_conflict_with_matching_result() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=False,
            ),
        ]
    )

    assert aggregated[0].conflict is True
    assert aggregated[0].manual_review_required is True


def test_selection_prefers_matches_reported_true_over_none_or_false() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=None,
                difference_percent_points=None,
                matches_reported=None,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=18.8,
                difference_percent_points=1.0,
                matches_reported=False,
            ),
        ]
    )

    assert aggregated[0].selected_metric.value == 19.8
    assert aggregated[0].selected_reason is not None
    assert "reported-match verification" in aggregated[0].selected_reason


def test_selection_prefers_reported_change_over_missing_reported_value() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_net_interest_income_yoy_growth",
                calculated_change_percent=13.44,
                reported_change_percent=None,
                difference_percent_points=None,
                matches_reported=None,
                source_trace_count=2,
            ),
            _make_result(
                "group_net_interest_income_yoy_growth",
                calculated_change_percent=13.44,
                reported_change_percent=13.44,
                difference_percent_points=0.0,
                matches_reported=None,
                source_trace_count=1,
            ),
        ]
    )

    assert aggregated[0].selected_audit_entry.output == 13.44
    assert aggregated[0].occurrence_count == 2
    assert aggregated[0].selected_reason is not None
    assert "reported change percentage" in aggregated[0].selected_reason


def test_first_seen_metric_order_is_preserved() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=6.81,
                reported_change_percent=6.81,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=6.81,
                reported_change_percent=6.81,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
        ]
    )

    assert [item.metric_name for item in aggregated] == [
        "group_total_assets_growth",
        "group_profit_for_the_period_yoy_growth",
    ]


def test_split_aggregated_metrics_returns_one_selected_metric_and_audit_per_name() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=6.81,
                reported_change_percent=6.81,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=6.81,
                reported_change_percent=6.81,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
        ]
    )

    metrics, audits = split_aggregated_metrics(aggregated)

    assert [metric.metric_name for metric in metrics] == [
        "group_total_assets_growth",
        "group_profit_for_the_period_yoy_growth",
    ]
    assert [audit.metric_name for audit in audits] == [
        "group_total_assets_growth",
        "group_profit_for_the_period_yoy_growth",
    ]


def test_has_metric_conflicts_returns_true_when_any_conflict_exists() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=6.81,
                reported_change_percent=6.81,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
            _make_result(
                "group_total_assets_growth",
                calculated_change_percent=7.21,
                reported_change_percent=7.21,
                difference_percent_points=0.0,
                matches_reported=True,
            ),
        ]
    )

    assert has_metric_conflicts(aggregated) is True


def test_aggregation_does_not_mutate_original_metric_verification_results() -> None:
    first = _make_result(
        "group_profit_for_the_period_yoy_growth",
        calculated_change_percent=19.8,
        reported_change_percent=19.8,
        difference_percent_points=0.0,
        matches_reported=True,
    )
    second = _make_result(
        "group_profit_for_the_period_yoy_growth",
        calculated_change_percent=19.8,
        reported_change_percent=None,
        difference_percent_points=None,
        matches_reported=None,
    )
    original_first = first.model_dump(mode="json")
    original_second = second.model_dump(mode="json")

    aggregate_metric_results([first, second])

    assert first.model_dump(mode="json") == original_first
    assert second.model_dump(mode="json") == original_second


def test_no_test_calls_deepseek_or_network() -> None:
    aggregated = aggregate_metric_results(
        [
            _make_result(
                "group_profit_for_the_period_yoy_growth",
                calculated_change_percent=19.8,
                reported_change_percent=19.8,
                difference_percent_points=0.0,
                matches_reported=True,
            )
        ]
    )

    assert aggregated[0].selected_metric.unit is MetricUnit.PERCENT
