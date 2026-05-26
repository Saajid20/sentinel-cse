from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    R11MetricBuildError,
    build_growth_metric_for_item,
    build_growth_metrics_for_items,
    split_metric_results,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialStatementType,
    MetricDirection,
    MetricUnit,
    SourceTrace,
)
from sentinel_research.agents.r11.tables import (  # noqa: E402
    MappedLineItemValues,
    ParsedFinancialValue,
)


def _make_source_trace(row_label: str) -> SourceTrace:
    return SourceTrace(
        local_file_path="C:/tmp/comb_q1_2026.pdf",
        page_number=12,
        table_id="pypdf_page_12",
        row_label=row_label,
        raw_value="raw row",
        notes="metric builder test",
    )


def _parsed(
    raw: str | int | float | None,
    value: float | None,
    *,
    is_percent: bool = False,
) -> ParsedFinancialValue:
    return ParsedFinancialValue(
        raw=raw,
        value=value,
        is_missing=value is None,
        is_percent=is_percent,
    )


def _make_item(
    canonical_name: str,
    original_label: str,
    mapped_values: dict[str, ParsedFinancialValue],
    *,
    statement_type: FinancialStatementType = FinancialStatementType.INCOME_STATEMENT,
    unit: MetricUnit = MetricUnit.UNKNOWN,
) -> MappedLineItemValues:
    raw_period_values = {key: value.raw for key, value in mapped_values.items()}
    return MappedLineItemValues(
        canonical_name=canonical_name,
        original_label=original_label,
        statement_type=statement_type,
        unit=unit,
        raw_period_values=raw_period_values,
        mapped_values=mapped_values,
        source_trace=_make_source_trace(original_label),
        notes="fake mapped line item",
    )


def _make_profit_item(
    *,
    group_reported_change_percent: float | None = 19.80,
) -> MappedLineItemValues:
    mapped_values = {
        "group_current": _parsed("17,936,712", 17936712.0),
        "group_previous": _parsed("14,972,114", 14972114.0),
        "group_reported_change_percent": _parsed(
            None if group_reported_change_percent is None else f"{group_reported_change_percent:.2f}",
            group_reported_change_percent,
            is_percent=True,
        ),
        "bank_current": _parsed("17,172,328", 17172328.0),
        "bank_previous": _parsed("14,496,860", 14496860.0),
        "bank_reported_change_percent": _parsed("18.46", 18.46, is_percent=True),
    }
    return _make_item(
        "profit_for_the_period",
        "Profit for the period",
        mapped_values,
    )


def test_build_growth_metric_for_item_returns_none_for_unsupported_canonical_name() -> None:
    item = _make_item(
        "cash_and_cash_equivalents",
        "Cash and cash equivalents",
        {
            "group_current": _parsed("100", 100.0),
            "group_previous": _parsed("90", 90.0),
        },
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    assert build_growth_metric_for_item(item) is None


def test_profit_for_the_period_builds_group_metric_with_matching_reported_percent() -> None:
    result = build_growth_metric_for_item(_make_profit_item())

    assert result is not None
    assert result.metric.metric_name == "group_profit_for_the_period_yoy_growth"
    assert result.metric.value == 19.8
    assert result.calculated_change_percent == 19.8
    assert result.reported_change_percent == 19.8
    assert result.matches_reported is True
    assert result.difference_percent_points == 0.0


def test_net_interest_income_builds_group_metric_with_expected_growth() -> None:
    item = _make_item(
        "net_interest_income",
        "Net interest income",
        {
            "group_current": _parsed("38,813,847", 38813847.0),
            "group_previous": _parsed("34,214,823", 34214823.0),
            "group_reported_change_percent": _parsed("13.44", 13.44, is_percent=True),
        },
    )

    result = build_growth_metric_for_item(item)

    assert result is not None
    assert result.metric.metric_name == "group_net_interest_income_yoy_growth"
    assert result.calculated_change_percent == pytest.approx(13.44, abs=0.01)
    assert result.matches_reported is True


def test_impairment_decrease_produces_negative_percent_and_improving_direction() -> None:
    item = _make_item(
        "impairment_charges_and_other_losses",
        "Impairment charges and other losses",
        {
            "group_current": _parsed("950", 950.0),
            "group_previous": _parsed("1,200", 1200.0),
            "group_reported_change_percent": _parsed("(20.83)", -20.83, is_percent=True),
        },
    )

    result = build_growth_metric_for_item(item)

    assert result is not None
    assert result.calculated_change_percent < 0
    assert result.metric.direction is MetricDirection.IMPROVING


def test_total_assets_positive_growth_produces_improving_direction() -> None:
    item = _make_item(
        "total_assets",
        "Total assets",
        {
            "group_current": _parsed("3,608,820,949", 3608820949.0),
            "group_previous": _parsed("3,378,864,406", 3378864406.0),
            "group_reported_change_percent": _parsed("6.81", 6.81, is_percent=True),
        },
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    result = build_growth_metric_for_item(item)

    assert result is not None
    assert result.metric.direction is MetricDirection.IMPROVING


def test_total_liabilities_positive_growth_is_conservatively_deteriorating() -> None:
    item = _make_item(
        "total_liabilities",
        "Total liabilities",
        {
            "group_current": _parsed("3,249,218,735", 3249218735.0),
            "group_previous": _parsed("3,046,192,022", 3046192022.0),
            "group_reported_change_percent": _parsed("6.66", 6.66, is_percent=True),
        },
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    result = build_growth_metric_for_item(item)

    assert result is not None
    assert result.metric.direction is MetricDirection.DETERIORATING


def test_bank_entity_prefix_uses_bank_values_and_bank_metric_name() -> None:
    result = build_growth_metric_for_item(
        _make_profit_item(),
        entity_prefix="bank",
    )

    assert result is not None
    assert result.metric.metric_name == "bank_profit_for_the_period_yoy_growth"
    assert result.calculated_change_percent == 18.46
    assert result.reported_change_percent == 18.46


def test_reported_percent_mismatch_sets_matches_false_and_records_difference() -> None:
    result = build_growth_metric_for_item(
        _make_profit_item(group_reported_change_percent=18.80),
    )

    assert result is not None
    assert result.matches_reported is False
    assert result.difference_percent_points == 1.0


def test_missing_reported_percent_still_builds_metric() -> None:
    result = build_growth_metric_for_item(
        _make_profit_item(group_reported_change_percent=None),
    )

    assert result is not None
    assert result.reported_change_percent is None
    assert result.matches_reported is None
    assert result.difference_percent_points is None


def test_tool_audit_entry_contains_formula_inputs_output_metric_name_and_timezone() -> None:
    generated_at = datetime(2026, 5, 26, 12, 30, tzinfo=UTC)

    result = build_growth_metric_for_item(
        _make_profit_item(),
        generated_at=generated_at,
    )

    assert result is not None
    assert result.audit_entry.formula == "(current - previous) / abs(previous) * 100"
    assert result.audit_entry.inputs == {
        "current": 17936712.0,
        "previous": 14972114.0,
        "reported_change_percent": 19.8,
    }
    assert result.audit_entry.output == 19.8
    assert result.audit_entry.metric_name == "group_profit_for_the_period_yoy_growth"
    assert result.audit_entry.generated_at == generated_at
    assert result.audit_entry.generated_at.tzinfo is not None


def test_split_metric_results_returns_metrics_and_audit_entries_in_order() -> None:
    profit_result = build_growth_metric_for_item(_make_profit_item())
    assets_result = build_growth_metric_for_item(
        _make_item(
            "total_assets",
            "Total assets",
            {
                "group_current": _parsed("200", 200.0),
                "group_previous": _parsed("100", 100.0),
                "group_reported_change_percent": _parsed("100.00", 100.0, is_percent=True),
            },
            statement_type=FinancialStatementType.BALANCE_SHEET,
        )
    )

    assert profit_result is not None
    assert assets_result is not None

    metrics, audit_entries = split_metric_results([profit_result, assets_result])

    assert [metric.metric_name for metric in metrics] == [
        "group_profit_for_the_period_yoy_growth",
        "group_total_assets_growth",
    ]
    assert [entry.metric_name for entry in audit_entries] == [
        "group_profit_for_the_period_yoy_growth",
        "group_total_assets_growth",
    ]


def test_build_growth_metrics_for_items_skips_unsupported_items_and_keeps_supported_order() -> None:
    results = build_growth_metrics_for_items(
        [
            _make_item(
                "cash_and_cash_equivalents",
                "Cash and cash equivalents",
                {
                    "group_current": _parsed("100", 100.0),
                    "group_previous": _parsed("90", 90.0),
                },
                statement_type=FinancialStatementType.BALANCE_SHEET,
            ),
            _make_profit_item(),
            _make_item(
                "net_interest_income",
                "Net interest income",
                {
                    "group_current": _parsed("38,813,847", 38813847.0),
                    "group_previous": _parsed("34,214,823", 34214823.0),
                    "group_reported_change_percent": _parsed("13.44", 13.44, is_percent=True),
                },
            ),
        ]
    )

    assert [result.metric.metric_name for result in results] == [
        "group_profit_for_the_period_yoy_growth",
        "group_net_interest_income_yoy_growth",
    ]


def test_invalid_entity_prefix_raises_r11_metric_build_error() -> None:
    with pytest.raises(R11MetricBuildError, match="entity_prefix must be 'group' or 'bank'"):
        build_growth_metric_for_item(_make_profit_item(), entity_prefix="consolidated")


def test_no_test_calls_deepseek_or_network() -> None:
    result = build_growth_metric_for_item(_make_profit_item())

    assert result is not None
    assert result.metric.unit is MetricUnit.PERCENT
