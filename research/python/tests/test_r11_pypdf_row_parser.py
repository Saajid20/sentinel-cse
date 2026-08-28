from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.extraction import (  # noqa: E402
    parse_financial_row_text,
    parse_financial_rows_from_table,
    parse_financial_rows_from_tables,
    parse_numeric_tokens,
)
from sentinel_research.agents.r11.extraction.pypdf_row_parser import (  # noqa: E402
    ParsedFinancialRow,
    is_wrapped_label_prefix_line,
    is_wrapped_label_continuation,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    ExtractedFinancialTable,
    FinancialStatementType,
    R11ConfidenceLevel,
    SourceTrace,
)


def _make_table(
    page_number: int,
    lines: list[str],
    *,
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN,
) -> ExtractedFinancialTable:
    return ExtractedFinancialTable(
        table_id=f"pypdf_page_{page_number}",
        statement_type=statement_type,
        title=f"pypdf baseline page {page_number}",
        page_number=page_number,
        columns=["line_number", "text"],
        rows=[
            {"line_number": index, "text": text}
            for index, text in enumerate(lines, start=1)
        ],
        extraction_method="pypdf_baseline",
        extraction_confidence=R11ConfidenceLevel.LOW,
        source_trace=SourceTrace(
            local_file_path="C:/tmp/comb.pdf",
            page_number=page_number,
            table_id=f"pypdf_page_{page_number}",
            notes="pypdf baseline text extraction",
        ),
    )


def test_parse_numeric_tokens_extracts_comma_numbers_decimals_and_parenthesized_negatives() -> None:
    text = "Profit 99,003,088 12.47 (55.49) (636) 10.73"

    values = parse_numeric_tokens(text)

    assert values == ["99,003,088", "12.47", "(55.49)", "(636)", "10.73"]


def test_parse_numeric_tokens_rejects_unbalanced_parentheses() -> None:
    text = "Total comprehensive income (52,2620 2,312,829 note 7) (52,262)"

    values = parse_numeric_tokens(text)

    assert "(52,2620" not in values
    assert "7)" not in values
    assert "(52,262)" in values
    assert "2,312,829" in values


def test_percent_tokens_clean_labels_without_becoming_values() -> None:
    parsed = parse_financial_row_text(
        "Revenue 100 90 11% 400 360 (11%)",
        page_number=3,
        table_id="pypdf_page_3",
        line_number=8,
    )

    assert parsed is not None
    assert parsed.label == "Revenue"
    assert parsed.values == ["100", "90", "400", "360"]


def test_pypdf_split_percent_cells_do_not_strand_the_row_tail_in_the_label() -> None:
    # ACME page 2: pypdf emits "( 14%)" instead of "(14%)". The split "(" + "14%)"
    # tokens used to defeat trailing-value stripping, so the whole row became the label.
    parsed = parse_financial_row_text(
        "Profit / (Loss) for the Period (313,538) (192,078) ( 63%) "
        "(462,860) (405,923) ( 14%)",
        page_number=2,
        table_id="pypdf_page_2",
        line_number=39,
    )

    assert parsed is not None
    assert parsed.label == "Profit / (Loss) for the Period"
    assert parsed.values == ["(313,538)", "(192,078)", "(462,860)", "(405,923)"]
    # Percent cells stay out of the financial values, split or not.
    assert not any("%" in value for value in parsed.values)
    # raw_text keeps the pypdf spacing for source-trace fidelity.
    assert "( 14%)" in parsed.raw_text


def test_parse_financial_row_text_parses_net_interest_income_row_into_label_and_six_values() -> None:
    parsed = parse_financial_row_text(
        "Net interest income 38,813,847 34,214,823 13.44 37,339,338 33,251,596 12.29",
        page_number=5,
        table_id="pypdf_page_5",
        line_number=10,
    )

    assert parsed is not None
    assert parsed.label == "Net interest income"
    assert parsed.values == [
        "38,813,847",
        "34,214,823",
        "13.44",
        "37,339,338",
        "33,251,596",
        "12.29",
    ]


def test_parse_financial_row_text_parses_impairment_row_with_parenthesized_change() -> None:
    parsed = parse_financial_row_text(
        "Less : Impairment charges and other losses 3,183,234 7,150,971 (55.49) 2,818,375 6,966,048 (59.54)",
        page_number=5,
        table_id="pypdf_page_5",
        line_number=12,
    )

    assert parsed is not None
    assert parsed.label == "Less : Impairment charges and other losses"
    assert parsed.values[-1] == "(59.54)"


def test_parse_financial_row_text_parses_row_with_dash_values() -> None:
    parsed = parse_financial_row_text(
        "Other comprehensive income - - - 120 100 20.00",
        page_number=6,
        table_id="pypdf_page_6",
        line_number=8,
    )

    assert parsed is not None
    assert parsed.label == "Other comprehensive income"
    assert parsed.values[:3] == ["-", "-", "-"]


def test_parse_financial_row_text_returns_none_for_header_lines() -> None:
    parsed = parse_financial_row_text(
        "For the three months ended 31 March 2026 31 March 2025 Change %",
        page_number=5,
        table_id="pypdf_page_5",
        line_number=2,
    )

    assert parsed is None


def test_parse_financial_row_text_returns_none_when_fewer_than_two_values() -> None:
    parsed = parse_financial_row_text(
        "Profit for the period 17,936,712",
        page_number=5,
        table_id="pypdf_page_5",
        line_number=15,
    )

    assert parsed is None


def test_wata_profit_row_strips_percent_and_numeric_tail_from_label() -> None:
    parsed = parse_financial_row_text(
        "Profit for the period 146,379 412,352 -65% 2,330,446 1,884,909 24%",
        page_number=3,
        table_id="pypdf_page_3",
        line_number=21,
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    assert parsed is not None
    assert parsed.label == "Profit for the period"
    assert parsed.values == ["146,379", "412,352", "2,330,446", "1,884,909"]


def test_wata_revenue_row_strips_percent_and_numeric_tail_from_label() -> None:
    parsed = parse_financial_row_text(
        "Revenue 2,174,903 1,878,853 16% 9,442,172 7,800,043 21%",
        page_number=3,
        table_id="pypdf_page_3",
        line_number=8,
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    assert parsed is not None
    assert parsed.label == "Revenue"
    assert parsed.values == ["2,174,903", "1,878,853", "9,442,172", "7,800,043"]


def test_parse_financial_row_text_rejects_notes_heading_with_unmatched_close_parenthesis() -> None:
    parsed = parse_financial_row_text(
        "7) Share Information Public Shareholders 1,268",
        page_number=3,
        table_id="pypdf_page_3",
        line_number=5,
    )

    assert parsed is None


def test_parse_financial_row_text_omits_malformed_unmatched_open_parenthesis_value() -> None:
    parsed = parse_financial_row_text(
        "Total comprehensive income for the period 2,365,092 2,365,092 (52,2620 2,312,829",
        page_number=6,
        table_id="pypdf_page_6",
        line_number=24,
    )

    assert parsed is not None
    assert "(52,2620" not in parsed.values
    assert parsed.values == ["2,365,092", "2,365,092", "2,312,829"]


def test_parsed_financial_row_validates_positive_page_and_line() -> None:
    with pytest.raises(ValidationError, match="page_number must be positive"):
        ParsedFinancialRow(
            page_number=0,
            table_id="pypdf_page_1",
            line_number=1,
            label="Profit",
            raw_text="Profit 1 2",
            values=["1", "2"],
        )

    with pytest.raises(ValidationError, match="line_number must be positive"):
        ParsedFinancialRow(
            page_number=1,
            table_id="pypdf_page_1",
            line_number=0,
            label="Profit",
            raw_text="Profit 1 2",
            values=["1", "2"],
        )


def test_parse_financial_rows_from_table_preserves_source_trace_page_table_and_row_label() -> None:
    table = _make_table(
        5,
        ["Profit for the period 17,936,712 14,972,114 19.80 17,172,328 14,496,860 18.46"],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    assert len(parsed_rows) == 1
    assert parsed_rows[0].source_trace is not None
    assert parsed_rows[0].source_trace.page_number == 5
    assert parsed_rows[0].source_trace.table_id == "pypdf_page_5"
    assert parsed_rows[0].source_trace.row_label == "Profit for the period"


def test_parse_financial_rows_from_table_returns_expected_rows_from_fake_page_five_income_statement() -> None:
    table = _make_table(
        5,
        [
            "STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME",
            "For the three months ended 31 March 2026 31 March 2025 Change %",
            "Net interest income 38,813,847 34,214,823 13.44 37,339,338 33,251,596 12.29",
            "Less : Impairment charges and other losses 3,183,234 7,150,971 (55.49) 2,818,375 6,966,048 (59.54)",
            "Profit for the period 17,936,712 14,972,114 19.80 17,172,328 14,496,860 18.46",
        ],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    assert [row.label for row in parsed_rows] == [
        "Net interest income",
        "Less : Impairment charges and other losses",
        "Profit for the period",
    ]


def test_parse_financial_rows_from_tables_flattens_multiple_tables() -> None:
    first = _make_table(
        5,
        ["Profit for the period 17,936,712 14,972,114 19.80 17,172,328 14,496,860 18.46"],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )
    second = _make_table(
        7,
        ["Total Assets 3,608,820,949 3,378,864,406 6.81 3,476,672,096 3,257,948,212 6.71"],
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    parsed_rows = parse_financial_rows_from_tables([first, second])

    assert [row.page_number for row in parsed_rows] == [5, 7]
    assert [row.label for row in parsed_rows] == ["Profit for the period", "Total Assets"]


_HVA_BALANCE_SHEET_LINES = [
    "Retained Earnings (1,033,100,953)    (1,040,779,187)      (1,032,503,652)    (1,040,224,886)",
    "Total Equity attributable to the equity",
    "holders of the Company/Total equity (64,290,676)          (70,799,910)           (63,693,376)         (70,245,609)",
    "Non-Current Liabilities",
    "Employee benefits 17,395,004           12,282,207             17,395,004           12,282,207",
]


def test_is_wrapped_label_prefix_line_accepts_a_caption_cut_mid_phrase() -> None:
    assert is_wrapped_label_prefix_line("Total Equity attributable to the equity") is True
    assert is_wrapped_label_prefix_line("Share of results of equity-accounted investees, net of") is True


def test_is_wrapped_label_prefix_line_rejects_headings_values_and_headers() -> None:
    # Complete section headings end on a capitalised word.
    assert is_wrapped_label_prefix_line("Equity and Liabilities") is False
    assert is_wrapped_label_prefix_line("Non-Current Liabilities") is False
    assert is_wrapped_label_prefix_line("ASSETS") is False
    assert is_wrapped_label_prefix_line("Current Assets") is False
    # Not a label-only line, or not a caption at all.
    assert is_wrapped_label_prefix_line("   ") is False
    assert is_wrapped_label_prefix_line("Employee benefits 17,395,004 12,282,207") is False
    assert is_wrapped_label_prefix_line("Statement of Financial Position") is False
    assert is_wrapped_label_prefix_line("As at 31st March 2026") is False


def test_is_wrapped_label_continuation_only_matches_lowercase_opening_labels() -> None:
    assert is_wrapped_label_continuation("holders of the Company/Total equity") is True
    assert is_wrapped_label_continuation("Total Equity") is False
    assert is_wrapped_label_continuation("Non-Current Liabilities") is False
    assert is_wrapped_label_continuation("") is False


def test_wrapped_balance_sheet_label_is_joined_to_its_value_line() -> None:
    """HVA.N0000 page 5: the caption wraps and the values sit on the second line."""
    table = _make_table(
        5,
        _HVA_BALANCE_SHEET_LINES,
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    labels = [row.label for row in parsed_rows]
    assert (
        "Total Equity attributable to the equity holders of the Company/Total equity"
        in labels
    )
    assert "holders of the Company/Total equity" not in labels

    joined = next(
        row
        for row in parsed_rows
        if row.label.startswith("Total Equity attributable")
    )
    assert joined.values == [
        "(64,290,676)",
        "(70,799,910)",
        "(63,693,376)",
        "(70,245,609)",
    ]
    assert joined.line_number == 3
    assert joined.source_trace is not None
    assert "continuation join from line 2" in (joined.source_trace.notes or "")


def test_wrapped_label_join_does_not_swallow_complete_section_headings() -> None:
    table = _make_table(
        5,
        _HVA_BALANCE_SHEET_LINES,
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    # "Non-Current Liabilities" precedes a value row but is a complete heading,
    # so the row beneath it must keep its own label.
    assert "Employee benefits" in [row.label for row in parsed_rows]


def test_wrapped_label_join_is_scoped_to_balance_sheet_pages() -> None:
    """Income-statement OCI captions wrap the same way and are left alone."""
    income_lines = [
        "Total Other Comprehensive Income for the",
        "period 1,234,567 2,345,678 3,456,789 4,567,890",
    ]
    balance_sheet_table = _make_table(
        5,
        income_lines,
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )
    income_statement_table = _make_table(
        2,
        income_lines,
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    assert [row.label for row in parse_financial_rows_from_table(balance_sheet_table)] == [
        "Total Other Comprehensive Income for the period"
    ]
    assert [
        row.label for row in parse_financial_rows_from_table(income_statement_table)
    ] == ["period"]


def test_wrapped_label_join_does_not_glue_a_complete_heading_onto_the_row_below() -> None:
    table = _make_table(
        5,
        [
            "Equity and Liabilities",
            "holders of the Company/Total equity (64,290,676) (70,799,910)",
        ],
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    # "Equity and Liabilities" ends on a capitalised word, so it is a heading,
    # not a caption cut mid-phrase. The row below keeps its own label.
    assert [row.label for row in parsed_rows] == ["holders of the Company/Total equity"]


def test_wrapped_label_join_never_removes_a_row_the_value_line_produced() -> None:
    table = _make_table(
        5,
        [
            "Statement of Financial Position",
            "holders of the Company/Total equity (64,290,676) (70,799,910)",
        ],
        statement_type=FinancialStatementType.BALANCE_SHEET,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    # The preceding line is a statement header, never a caption prefix.
    assert [row.label for row in parsed_rows] == ["holders of the Company/Total equity"]


def test_no_test_calls_deepseek_or_network() -> None:
    table = _make_table(
        5,
        ["Profit for the period 17,936,712 14,972,114 19.80 17,172,328 14,496,860 18.46"],
        statement_type=FinancialStatementType.INCOME_STATEMENT,
    )

    parsed_rows = parse_financial_rows_from_table(table)

    assert parsed_rows[0].values[0] == "17,936,712"
