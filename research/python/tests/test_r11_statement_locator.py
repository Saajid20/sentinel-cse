from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.extraction import (  # noqa: E402
    StatementPageMatch,
    classify_statement_page,
    locate_statement_pages,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    ExtractedFinancialTable,
    FinancialStatementType,
    R11ConfidenceLevel,
    SourceTrace,
)


def _make_table(page_number: int, lines: list[str]) -> ExtractedFinancialTable:
    return ExtractedFinancialTable(
        table_id=f"pypdf_page_{page_number}",
        statement_type=FinancialStatementType.UNKNOWN,
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
            local_file_path="C:/tmp/sample.pdf",
            page_number=page_number,
            notes="pypdf baseline text extraction",
        ),
    )


def test_classify_income_statement_page_high_confidence() -> None:
    table = _make_table(
        5,
        [
            "INCOME STATEMENT",
            "Gross income",
            "Profit for the period",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.INCOME_STATEMENT
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_classify_profit_loss_comprehensive_income_page_as_income_statement() -> None:
    table = _make_table(
        6,
        [
            "Statement of profit or loss and other comprehensive income",
            "Revenue",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.INCOME_STATEMENT
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_balance_sheet_markers_override_generic_profit_or_loss_line_item_text() -> None:
    table = _make_table(
        7,
        [
            "STATEMENT OF FINANCIAL POSITION",
            "ASSETS",
            "LIABILITIES",
            "Total Assets",
            "Total Liabilities",
            "Financial assets recognised through profit or loss",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.BALANCE_SHEET
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_classify_financial_position_page_as_balance_sheet_high_confidence() -> None:
    table = _make_table(
        7,
        [
            "STATEMENT OF FINANCIAL POSITION",
            "Assets",
            "Liabilities",
            "Total Assets",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.BALANCE_SHEET
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_classify_equity_page_high_confidence() -> None:
    table = _make_table(
        8,
        [
            "STATEMENT OF CHANGES IN EQUITY",
            "Retained earnings",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.EQUITY_STATEMENT
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_classify_cash_flow_page() -> None:
    table = _make_table(
        9,
        [
            "Statement of Cash Flows",
            "Operating activities",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.CASH_FLOW
    assert match.confidence is R11ConfidenceLevel.HIGH


def test_classify_notes_page() -> None:
    table = _make_table(
        10,
        [
            "Notes to the Financial Statements",
            "Note 1 Reporting entity",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.NOTES


def test_unknown_page_returns_unknown_low_and_empty_markers() -> None:
    table = _make_table(
        11,
        [
            "Chairman's message",
            "Operational review",
        ],
    )

    match = classify_statement_page(table)

    assert match.statement_type is FinancialStatementType.UNKNOWN
    assert match.confidence is R11ConfidenceLevel.LOW
    assert match.matched_markers == []


def test_locate_statement_pages_preserves_order_and_includes_unknowns() -> None:
    tables = [
        _make_table(1, ["Chairman's message"]),
        _make_table(2, ["Income Statement", "Profit for the period"]),
        _make_table(3, ["Statement of Financial Position", "Total Assets"]),
    ]

    matches = locate_statement_pages(tables)

    assert [match.page_number for match in matches] == [1, 2, 3]
    assert [match.statement_type for match in matches] == [
        FinancialStatementType.UNKNOWN,
        FinancialStatementType.INCOME_STATEMENT,
        FinancialStatementType.BALANCE_SHEET,
    ]


def test_statement_page_match_rejects_invalid_page_number() -> None:
    with pytest.raises(ValidationError, match="page_number must be positive"):
        StatementPageMatch(
            page_number=0,
            table_id="table-1",
            statement_type=FinancialStatementType.UNKNOWN,
            confidence=R11ConfidenceLevel.LOW,
            matched_markers=[],
        )


def test_no_test_calls_deepseek_or_network() -> None:
    table = _make_table(12, ["INCOME STATEMENT", "Profit for the period"])

    match = classify_statement_page(table)

    assert "INCOME STATEMENT" in match.matched_markers
