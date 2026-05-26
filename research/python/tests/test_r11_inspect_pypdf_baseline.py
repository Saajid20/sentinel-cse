from __future__ import annotations

import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PYTHON_ROOT / "scripts"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest

from r11_inspect_pypdf_baseline import (  # noqa: E402
    _filter_tables,
    _line_context,
    _matching_line_numbers,
    _table_matches_search,
    _validate_page_range,
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


def test_page_range_filters_tables_correctly() -> None:
    tables = [
        _make_table(1, ["income statement", "profit"]),
        _make_table(2, ["balance sheet", "total assets"]),
        _make_table(3, ["cash flow", "operating activities"]),
    ]

    filtered = _filter_tables(tables, start_page=2, end_page=3)

    assert [table.page_number for table in filtered] == [2, 3]


def test_search_matches_case_insensitively() -> None:
    table = _make_table(1, ["Income Statement", "Profit after tax"])

    assert _table_matches_search(table, ["income statement"])
    assert _table_matches_search(table, ["PROFIT"])


def test_repeated_search_terms_match_any_term() -> None:
    table = _make_table(1, ["Balance Sheet", "Total Assets"])

    assert _table_matches_search(table, ["income", "total assets"])


def test_matching_line_numbers_are_returned() -> None:
    table = _make_table(1, ["Income Statement", "Profit after tax", "Total assets"])

    assert _matching_line_numbers(table, ["profit", "assets"]) == [2, 3]


def test_context_lines_include_before_after_bounds_safely() -> None:
    table = _make_table(1, ["L1", "L2", "L3", "L4"])

    first_context = _line_context(table.rows, 1, 1)
    middle_context = _line_context(table.rows, 3, 1)

    assert [row["text"] for row in first_context] == ["L1", "L2"]
    assert [row["text"] for row in middle_context] == ["L2", "L3", "L4"]


def test_invalid_page_range_raises_value_error() -> None:
    with pytest.raises(ValueError, match="start_page must be <= end_page"):
        _validate_page_range(5, 3)


def test_no_test_calls_deepseek_or_network() -> None:
    table = _make_table(1, ["Income Statement", "Profit after tax"])

    filtered = _filter_tables([table], search_terms=["profit"])

    assert filtered[0].rows[1]["text"] == "Profit after tax"
