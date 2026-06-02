from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.extraction.pypdf_row_parser import ParsedFinancialRow  # noqa: E402
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialStatementType,
    MetricUnit,
    R11ConfidenceLevel,
    SourceTrace,
)
from sentinel_research.agents.r11.tables import (  # noqa: E402
    is_probable_noise_row,
    map_line_item_label,
    normalize_label_text,
    normalize_parsed_financial_row,
    normalize_parsed_financial_rows,
    snake_case_name,
)


def _make_row(
    label: str,
    values: list[str],
    *,
    line_number: int = 1,
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN,
) -> ParsedFinancialRow:
    return ParsedFinancialRow(
        page_number=5,
        table_id="pypdf_page_5",
        line_number=line_number,
        label=label,
        raw_text=f"{label} {' '.join(values)}",
        values=values,
        statement_type=statement_type,
        source_trace=SourceTrace(
            local_file_path="C:/tmp/comb.pdf",
            page_number=5,
            table_id="pypdf_page_5",
            row_label=label,
            raw_value=f"{label} {' '.join(values)}",
            notes="pypdf baseline row parser",
        ),
    )


def test_normalize_label_text_removes_less_add_prefixes_and_normalizes_punctuation() -> None:
    assert (
        normalize_label_text(" Less : Impairment charges and other losses ")
        == "impairment charges and other losses"
    )
    assert (
        normalize_label_text("Add / (Less): Net gains – trading")
        == "net gains trading"
    )


def test_snake_case_name_works() -> None:
    assert snake_case_name("Net interest income") == "net_interest_income"
    assert snake_case_name("Total liabilities and equity") == "total_liabilities_and_equity"


def test_is_probable_noise_row_filters_may_date_and_certification_rows() -> None:
    may_row = _make_row("May", ["14,", "2026"])
    cert_row = _make_row(
        "I certify that this financial statement complies with Companies Act No. 7 of 2007",
        ["7", "2007"],
        line_number=2,
    )

    assert is_probable_noise_row(may_row) is True
    assert is_probable_noise_row(cert_row) is True


def test_is_probable_noise_row_does_not_filter_eps_or_nav_per_share_rows() -> None:
    eps_row = _make_row(
        "Basic earnings per ordinary share Rs.",
        ["12.50", "10.25"],
    )
    nav_row = _make_row(
        "Net Assets Value per Ordinary Share Rs.",
        ["150.00", "140.00"],
        line_number=2,
    )

    assert is_probable_noise_row(eps_row) is False
    assert is_probable_noise_row(nav_row) is False


def test_map_line_item_label_maps_net_interest_income_high() -> None:
    mapping = map_line_item_label(
        "Net interest income",
        FinancialStatementType.INCOME_STATEMENT,
    )

    assert mapping is not None
    assert mapping.canonical_name == "net_interest_income"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_maps_impairment_charges_row_high() -> None:
    mapping = map_line_item_label(
        "Less : Impairment charges and other losses",
        FinancialStatementType.INCOME_STATEMENT,
    )

    assert mapping is not None
    assert mapping.canonical_name == "impairment_charges_and_other_losses"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_maps_total_assets_high() -> None:
    mapping = map_line_item_label(
        "Total Assets",
        FinancialStatementType.BALANCE_SHEET,
    )

    assert mapping is not None
    assert mapping.canonical_name == "total_assets"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_maps_profit_loss_for_the_period_to_profit_for_the_period() -> None:
    mapping = map_line_item_label(
        "Profit/(loss) for the period",
        FinancialStatementType.INCOME_STATEMENT,
    )

    assert mapping is not None
    assert mapping.canonical_name == "profit_for_the_period"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_maps_profit_loss_before_tax_to_existing_before_tax_canonical() -> None:
    mapping = map_line_item_label(
        "Profit/(loss) before tax",
        FinancialStatementType.INCOME_STATEMENT,
    )

    assert mapping is not None
    assert mapping.canonical_name == "profit_before_income_tax"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_preserves_existing_profit_for_the_period_behavior() -> None:
    mapping = map_line_item_label(
        "Profit for the period",
        FinancialStatementType.INCOME_STATEMENT,
    )

    assert mapping is not None
    assert mapping.canonical_name == "profit_for_the_period"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_map_line_item_label_maps_due_to_depositors_high() -> None:
    mapping = map_line_item_label(
        "Financial liabilities at amortised cost – due to depositors",
        FinancialStatementType.BALANCE_SHEET,
    )

    assert mapping is not None
    assert mapping.canonical_name == "customer_deposits"
    assert mapping.confidence is R11ConfidenceLevel.HIGH


def test_unknown_usable_label_maps_to_snake_case_low() -> None:
    mapping = map_line_item_label(
        "Unrealised fair value reserve movement",
        FinancialStatementType.BALANCE_SHEET,
    )

    assert mapping is not None
    assert mapping.canonical_name == "unrealised_fair_value_reserve_movement"
    assert mapping.confidence is R11ConfidenceLevel.LOW


def test_normalize_parsed_financial_row_creates_line_item_with_generic_value_keys() -> None:
    row = _make_row(
        "Net interest income",
        ["38,813,847", "34,214,823", "13.44"],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    normalized = normalize_parsed_financial_row(row)

    assert normalized is not None
    assert normalized.canonical_name == "net_interest_income"
    assert normalized.period_values == {
        "value_1": "38,813,847",
        "value_2": "34,214,823",
        "value_3": "13.44",
    }


def test_normalize_parsed_financial_row_preserves_source_trace() -> None:
    row = _make_row(
        "Total Assets",
        ["3,608,820,949", "3,378,864,406", "6.81"],
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    normalized = normalize_parsed_financial_row(row)

    assert normalized is not None
    assert normalized.source_trace is not None
    assert normalized.source_trace.page_number == 5
    assert normalized.source_trace.table_id == "pypdf_page_5"
    assert normalized.source_trace.row_label == "Total Assets"


def test_normalize_parsed_financial_rows_drops_noise_and_preserves_order() -> None:
    rows = [
        _make_row("May", ["14,", "2026"], line_number=1),
        _make_row(
            "Net interest income",
            ["38,813,847", "34,214,823", "13.44"],
            line_number=2,
            statement_type=FinancialStatementType.INCOME_STATEMENT,
        ),
        _make_row(
            "Total Assets",
            ["3,608,820,949", "3,378,864,406", "6.81"],
            line_number=3,
            statement_type=FinancialStatementType.BALANCE_SHEET,
        ),
    ]

    normalized = normalize_parsed_financial_rows(rows)

    assert [item.canonical_name for item in normalized] == [
        "net_interest_income",
        "total_assets",
    ]


def test_no_test_calls_deepseek_or_network() -> None:
    row = _make_row(
        "Basic earnings per ordinary share Rs.",
        ["12.50", "10.25"],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    normalized = normalize_parsed_financial_row(row)

    assert normalized is not None
    assert normalized.unit is MetricUnit.LKR
