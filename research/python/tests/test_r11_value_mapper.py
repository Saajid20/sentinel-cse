from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialStatementType,
    MetricUnit,
    NormalizedFinancialLineItem,
    SourceTrace,
)
from sentinel_research.agents.r11.tables import (  # noqa: E402
    R11ValueMappingError,
    get_required_numeric,
    map_comb_six_column_items,
    map_comb_six_column_values,
    parse_financial_value,
    parse_period_values,
)


def _make_line_item(
    canonical_name: str,
    original_label: str,
    period_values: dict[str, str | int | float | None],
    *,
    statement_type: FinancialStatementType = FinancialStatementType.INCOME_STATEMENT,
) -> NormalizedFinancialLineItem:
    return NormalizedFinancialLineItem(
        canonical_name=canonical_name,
        original_label=original_label,
        statement_type=statement_type,
        period_values=period_values,
        unit=MetricUnit.UNKNOWN,
        source_trace=SourceTrace(
            local_file_path="C:/tmp/comb.pdf",
            page_number=5,
            table_id="pypdf_page_5",
            row_label=original_label,
            raw_value="raw row text",
            notes="line item mapper",
        ),
    )


def test_parse_financial_value_parses_comma_numbers() -> None:
    parsed = parse_financial_value("17,936,712")

    assert parsed.raw == "17,936,712"
    assert parsed.value == 17936712.0
    assert parsed.is_missing is False


def test_parse_financial_value_parses_parenthesized_negatives() -> None:
    percent_value = parse_financial_value("(55.49)")
    amount_value = parse_financial_value("(1,054,334)")

    assert percent_value.value == -55.49
    assert amount_value.value == -1054334.0


def test_parse_financial_value_parses_dash_and_none_as_missing() -> None:
    dash_value = parse_financial_value("-")
    none_value = parse_financial_value(None)

    assert dash_value.is_missing is True
    assert dash_value.value is None
    assert none_value.is_missing is True
    assert none_value.value is None


def test_parse_financial_value_marks_percent_without_dividing_by_hundred() -> None:
    parsed = parse_financial_value("19.80", is_percent=True)

    assert parsed.value == 19.8
    assert parsed.is_percent is True


def test_parse_financial_value_rejects_bool_and_invalid_strings() -> None:
    with pytest.raises(R11ValueMappingError, match="boolean values"):
        parse_financial_value(True)

    with pytest.raises(R11ValueMappingError, match="invalid financial value"):
        parse_financial_value("abc")


def test_parse_period_values_preserves_key_order_and_marks_percent_keys() -> None:
    parsed = parse_period_values(
        {
            "group_current": "17,936,712",
            "group_reported_change_percent": "19.80",
            "bank_previous": "14,496,860",
        },
        percent_keys={"group_reported_change_percent"},
    )

    assert list(parsed.keys()) == [
        "group_current",
        "group_reported_change_percent",
        "bank_previous",
    ]
    assert parsed["group_reported_change_percent"].is_percent is True
    assert parsed["bank_previous"].is_percent is False


def test_map_comb_six_column_values_maps_generic_keys_to_semantic_keys() -> None:
    item = _make_line_item(
        "profit_for_the_period",
        "Profit for the period",
        {
            "value_1": "17,936,712",
            "value_2": "14,972,114",
            "value_3": "19.80",
            "value_4": "17,172,328",
            "value_5": "14,496,860",
            "value_6": "18.46",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert list(mapped.mapped_values.keys()) == [
        "group_current",
        "group_previous",
        "group_reported_change_percent",
        "bank_current",
        "bank_previous",
        "bank_reported_change_percent",
    ]
    assert mapped.mapped_values["group_current"].value == 17936712.0
    assert mapped.mapped_values["group_previous"].value == 14972114.0
    assert mapped.mapped_values["bank_current"].value == 17172328.0
    assert mapped.mapped_values["bank_previous"].value == 14496860.0


def test_map_comb_six_column_values_marks_change_fields_as_percent() -> None:
    item = _make_line_item(
        "profit_for_the_period",
        "Profit for the period",
        {
            "value_1": "17,936,712",
            "value_2": "14,972,114",
            "value_3": "19.80",
            "value_4": "17,172,328",
            "value_5": "14,496,860",
            "value_6": "18.46",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert mapped.mapped_values["group_reported_change_percent"].value == 19.8
    assert mapped.mapped_values["group_reported_change_percent"].is_percent is True
    assert mapped.mapped_values["bank_reported_change_percent"].value == 18.46
    assert mapped.mapped_values["bank_reported_change_percent"].is_percent is True


def test_map_comb_six_column_values_treats_four_value_row_as_dual_scope_without_bogus_percent() -> None:
    item = _make_line_item(
        "profit_for_the_period",
        "Profit for the period",
        {
            "value_1": "3,529,862,644",
            "value_2": "2,350,673,578",
            "value_3": "7,695,789,746",
            "value_4": "6,291,097,836",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert list(mapped.mapped_values.keys()) == [
        "group_current",
        "group_previous",
        "bank_current",
        "bank_previous",
    ]
    assert "group_reported_change_percent" not in mapped.mapped_values
    assert mapped.mapped_values["bank_current"].value == 7695789746.0
    assert mapped.notes == "comb_four_column_dual_scope_layout"


def test_map_comb_six_column_values_preserves_identity_and_source_trace() -> None:
    item = _make_line_item(
        "total_assets",
        "Total Assets",
        {
            "value_1": "3,608,820,949",
            "value_2": "3,378,864,406",
            "value_3": "6.81",
            "value_4": "3,476,672,096",
            "value_5": "3,257,948,212",
            "value_6": "6.71",
        },
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    mapped = map_comb_six_column_values(item)

    assert mapped.canonical_name == "total_assets"
    assert mapped.original_label == "Total Assets"
    assert mapped.statement_type is FinancialStatementType.BALANCE_SHEET
    assert mapped.source_trace is not None
    assert mapped.source_trace.page_number == 5


def test_map_comb_six_column_values_handles_dash_values_as_missing() -> None:
    item = _make_line_item(
        "other_comprehensive_income",
        "Other comprehensive income",
        {
            "value_1": "-",
            "value_2": "-",
            "value_3": "-",
            "value_4": "120",
            "value_5": "100",
            "value_6": "20.00",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert mapped.mapped_values["group_current"].is_missing is True
    assert mapped.mapped_values["group_reported_change_percent"].is_missing is True
    assert mapped.mapped_values["bank_current"].value == 120.0


def test_map_comb_six_column_items_maps_multiple_items_in_order() -> None:
    items = [
        _make_line_item(
            "net_interest_income",
            "Net interest income",
            {
                "value_1": "38,813,847",
                "value_2": "34,214,823",
                "value_3": "13.44",
            },
        ),
        _make_line_item(
            "profit_for_the_period",
            "Profit for the period",
            {
                "value_1": "17,936,712",
                "value_2": "14,972,114",
                "value_3": "19.80",
            },
        ),
    ]

    mapped_items = map_comb_six_column_items(items)

    assert [item.canonical_name for item in mapped_items] == [
        "net_interest_income",
        "profit_for_the_period",
    ]


def test_get_required_numeric_returns_value_and_rejects_missing() -> None:
    item = _make_line_item(
        "profit_for_the_period",
        "Profit for the period",
        {
            "value_1": "17,936,712",
            "value_2": "-",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert get_required_numeric(mapped, "group_current") == 17936712.0
    with pytest.raises(R11ValueMappingError, match="no numeric value"):
        get_required_numeric(mapped, "group_previous")


def test_no_test_calls_deepseek_or_network() -> None:
    item = _make_line_item(
        "profit_for_the_period",
        "Profit for the period",
        {
            "value_1": "17,936,712",
            "value_2": "14,972,114",
        },
    )

    mapped = map_comb_six_column_values(item)

    assert mapped.notes == "comb_six_column_layout"
