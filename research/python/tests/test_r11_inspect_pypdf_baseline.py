from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PYTHON_ROOT / "scripts"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest

from r11_inspect_pypdf_baseline import (  # noqa: E402
    _build_deterministic_analysis_payload,
    _build_verified_metric_results_for_mapped_items,
    _filter_tables,
    _line_context,
    _matching_line_numbers,
    _table_matches_search,
    _validate_page_range,
)
from sentinel_research.agents.r11.analysis.metric_builder import (  # noqa: E402
    MetricVerificationResult,
    R11MetricBuildError,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    ExtractedFinancialTable,
    FinancialMetric,
    FinancialStatementType,
    MetricDirection,
    MetricUnit,
    R11ConfidenceLevel,
    SourceTrace,
    ToolAuditEntry,
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


def _make_metric_verification_result(metric_name: str) -> MetricVerificationResult:
    source_trace = SourceTrace(
        local_file_path="C:/tmp/sample.pdf",
        page_number=1,
        table_id="pypdf_page_1",
        row_label="Profit for the period",
        raw_value="17,936,712",
        notes="inspection test",
    )
    metric = FinancialMetric(
        metric_name=metric_name,
        display_name=metric_name.replace("_", " ").title(),
        value=19.8,
        unit=MetricUnit.PERCENT,
        period="current",
        comparison_period="previous",
        direction=MetricDirection.IMPROVING,
        calculation_audit_id=f"audit_{metric_name}",
        source_traces=[source_trace],
        notes="inspection test metric",
    )
    audit_entry = ToolAuditEntry(
        tool_name="r11_calculation_toolbox",
        operation="calculate_yoy_growth",
        metric_name=metric_name,
        formula="(current - previous) / abs(previous) * 100",
        inputs={"current": 120.0, "previous": 100.0},
        output=19.8,
        generated_at=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
        source_traces=[source_trace],
        notes="inspection test audit",
    )
    return MetricVerificationResult(
        metric=metric,
        audit_entry=audit_entry,
        reported_change_percent=19.8,
        calculated_change_percent=19.8,
        difference_percent_points=0.0,
        matches_reported=True,
        tolerance_percent_points=0.05,
        notes="inspection test result",
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


def test_invalid_supported_metric_candidate_does_not_abort_and_records_warning(
    monkeypatch,
) -> None:
    valid_item = SimpleNamespace(canonical_name="gross_income")
    invalid_item = SimpleNamespace(canonical_name="profit_for_the_period")

    def fake_build_growth_metric_for_item(item, *, entity_prefix: str):
        assert entity_prefix == "group"
        if item.canonical_name == "profit_for_the_period":
            raise R11MetricBuildError(
                "failed to build metric for profit_for_the_period: "
                "profit_for_the_period has no numeric value for group_current"
            )
        return _make_metric_verification_result("group_gross_income_growth")

    monkeypatch.setattr(
        "r11_inspect_pypdf_baseline.build_growth_metric_for_item",
        fake_build_growth_metric_for_item,
    )

    verified_results, warnings = _build_verified_metric_results_for_mapped_items(
        [valid_item, invalid_item],
        metric_entity="group",
    )

    assert [result.metric.metric_name for result in verified_results] == [
        "group_gross_income_growth"
    ]
    assert warnings == [
        "failed to build metric for profit_for_the_period: "
        "profit_for_the_period has no numeric value for group_current"
    ]


def test_analysis_payload_records_metric_build_warnings() -> None:
    table = _make_table(1, ["Income Statement", "Profit after tax"])
    payload = _build_deterministic_analysis_payload(
        pdf_path=Path("C:/tmp/sample.pdf"),
        tables=[table],
        filtered_tables=[table],
        shown_tables=[table],
        statement_matches=[],
        search_terms=None,
        start_page=1,
        end_page=1,
        verified_metric_results=[
            _make_metric_verification_result("group_profit_for_the_period_yoy_growth")
        ],
        aggregated_metric_results=[],
        metric_build_warnings=[
            "failed to build metric for profit_for_the_period: "
            "profit_for_the_period has no numeric value for group_current"
        ],
        scorecard_build_result=None,
        scorecard_build_error=None,
        generated_at=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
    )

    assert payload["metric_build_warnings"] == [
        "failed to build metric for profit_for_the_period: "
        "profit_for_the_period has no numeric value for group_current"
    ]
    assert any(
        "Skipped 1 invalid metric candidate(s)" in note
        for note in payload["notes"]
    )


def test_no_test_calls_deepseek_or_network() -> None:
    table = _make_table(1, ["Income Statement", "Profit after tax"])

    filtered = _filter_tables([table], search_terms=["profit"])

    assert filtered[0].rows[1]["text"] == "Profit after tax"
