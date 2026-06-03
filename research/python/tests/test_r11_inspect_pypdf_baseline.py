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
    _build_verified_metric_results_for_tables,
    _filter_redundant_metric_candidates,
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
from sentinel_research.agents.r11.tables import (  # noqa: E402
    MappedLineItemValues,
    ParsedFinancialValue,
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


def test_filter_redundant_metric_candidates_drops_subset_duplicate_without_reported_percent() -> None:
    source_trace = SourceTrace(
        local_file_path="C:/tmp/sample.pdf",
        page_number=2,
        table_id="pypdf_page_2",
        row_label="Profit for the period",
        raw_value="raw row text",
        notes="inspection test",
    )
    primary = MappedLineItemValues(
        canonical_name="profit_for_the_period",
        original_label="Profit for the period",
        statement_type=FinancialStatementType.INCOME_STATEMENT,
        unit=MetricUnit.UNKNOWN,
        raw_period_values={
            "value_1": "3,529,862,644",
            "value_2": "2,350,673,578",
            "value_3": "50",
            "value_4": "7,695,789,746",
            "value_5": "6,291,097,836",
            "value_6": "22",
        },
        mapped_values={
            "group_current": ParsedFinancialValue(raw="3,529,862,644", value=3529862644.0),
            "group_previous": ParsedFinancialValue(raw="2,350,673,578", value=2350673578.0),
            "group_reported_change_percent": ParsedFinancialValue(
                raw="50",
                value=50.0,
                is_percent=True,
            ),
            "bank_current": ParsedFinancialValue(raw="7,695,789,746", value=7695789746.0),
            "bank_previous": ParsedFinancialValue(raw="6,291,097,836", value=6291097836.0),
            "bank_reported_change_percent": ParsedFinancialValue(
                raw="22",
                value=22.0,
                is_percent=True,
            ),
        },
        source_trace=source_trace,
        notes="primary row",
    )
    repeated_subtotal = MappedLineItemValues(
        canonical_name="profit_for_the_period",
        original_label="Profit for the period",
        statement_type=FinancialStatementType.INCOME_STATEMENT,
        unit=MetricUnit.UNKNOWN,
        raw_period_values={
            "value_1": "3,529,862,644",
            "value_2": "2,350,673,578",
            "value_3": "7,695,789,746",
            "value_4": "6,291,097,836",
        },
        mapped_values={
            "group_current": ParsedFinancialValue(raw="3,529,862,644", value=3529862644.0),
            "group_previous": ParsedFinancialValue(raw="2,350,673,578", value=2350673578.0),
            "bank_current": ParsedFinancialValue(raw="7,695,789,746", value=7695789746.0),
            "bank_previous": ParsedFinancialValue(raw="6,291,097,836", value=6291097836.0),
        },
        source_trace=source_trace,
        notes="repeated subtotal row",
    )

    filtered = _filter_redundant_metric_candidates(
        [primary, repeated_subtotal],
        metric_entity="group",
    )

    assert filtered == [primary]


def test_group_metric_source_selection_prefers_group_marked_income_statement_table(
    monkeypatch,
) -> None:
    group_table = _make_table(
        2,
        [
            "Income Statement",
            "Profit for the period 100 90 11 400 360 11",
            "Equity holders of the parent 95 85",
            "Non-controlling interest 5 5",
        ],
    )
    standalone_table = _make_table(
        3,
        [
            "Income Statement",
            "Profit for the period 80 70 14 300 290 3",
        ],
    )
    calls: list[int] = []

    def fake_build_verified_metric_results_for_table(*, table, statement_match, metric_entity):
        calls.append(table.page_number)
        return [_make_metric_verification_result(f"group_metric_page_{table.page_number}")], []

    monkeypatch.setattr(
        "r11_inspect_pypdf_baseline._build_verified_metric_results_for_table",
        fake_build_verified_metric_results_for_table,
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[group_table, standalone_table],
        statement_matches_by_key={
            ("pypdf_page_2", 2): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            ),
            ("pypdf_page_3", 3): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            ),
        },
        metric_entity="group",
    )

    assert calls == [2]
    assert [result.metric.metric_name for result in verified_results] == ["group_metric_page_2"]
    assert warnings == []


def test_group_metric_source_selection_keeps_all_income_statement_tables_without_group_markers(
    monkeypatch,
) -> None:
    first_table = _make_table(
        2,
        [
            "Income Statement",
            "Profit for the period 100 90 11 400 360 11",
        ],
    )
    second_table = _make_table(
        3,
        [
            "Income Statement",
            "Profit for the period 80 70 14 300 290 3",
        ],
    )
    calls: list[int] = []

    def fake_build_verified_metric_results_for_table(*, table, statement_match, metric_entity):
        calls.append(table.page_number)
        return [_make_metric_verification_result(f"group_metric_page_{table.page_number}")], []

    monkeypatch.setattr(
        "r11_inspect_pypdf_baseline._build_verified_metric_results_for_table",
        fake_build_verified_metric_results_for_table,
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[first_table, second_table],
        statement_matches_by_key={
            ("pypdf_page_2", 2): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            ),
            ("pypdf_page_3", 3): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            ),
        },
        metric_entity="group",
    )

    assert calls == [2, 3]
    assert [result.metric.metric_name for result in verified_results] == [
        "group_metric_page_2",
        "group_metric_page_3",
    ]
    assert warnings == []


def test_equity_statement_profit_rows_do_not_produce_profit_growth_metric() -> None:
    table = _make_table(
        6,
        [
            "Condensed Statement of changes in equity - Group",
            "Profit for the period 1,917,871 1,917,871 (32,962) 1,884,909",
            "Profit for the period 2,365,092 2,365,092 (52,262) 2,312,829",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_6", 6): SimpleNamespace(
                statement_type=FinancialStatementType.EQUITY_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert verified_results == []
    assert warnings == []


def test_unknown_segmental_analysis_profit_rows_do_not_produce_profit_growth_metric() -> None:
    table = _make_table(
        9,
        [
            "Segmental Analysis - Group",
            "Palm Oil Dairy Others Inter Segment Total",
            "Profit/(loss) for the year 2,735,648 1,953,250 (576,687) (327,038) (166,055) (434,980) 337,540 693,677 2,330,446 1,884,909",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_9", 9): SimpleNamespace(
                statement_type=FinancialStatementType.UNKNOWN
            )
        },
        metric_entity="group",
    )

    assert verified_results == []
    assert warnings == []


def test_primary_income_statement_profit_row_still_produces_profit_growth_metric() -> None:
    table = _make_table(
        5,
        [
            "Income Statement",
            "Profit for the period 100 80 25",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_5", 5): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert [result.metric.metric_name for result in verified_results] == [
        "group_profit_for_the_period_yoy_growth"
    ]
    assert verified_results[0].calculated_change_percent == 25.0
    assert verified_results[0].reported_change_percent == 25.0
    assert verified_results[0].matches_reported is True
    assert warnings == []


def test_quarter_plus_annual_consolidated_income_row_uses_annual_group_values() -> None:
    table = _make_table(
        3,
        [
            "Condensed Consolidated Income Statement",
            "Quarter ended 31 March 12 months ended 31 March",
            "2026 2025 Change % 2026 2025 Change %",
            "Profit for the period 146,379 412,352 -65% 2,330,446 1,884,909 24%",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_3", 3): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert [result.metric.metric_name for result in verified_results] == [
        "group_profit_for_the_period_yoy_growth"
    ]
    assert verified_results[0].audit_entry.inputs["current"] == 2330446.0
    assert verified_results[0].audit_entry.inputs["previous"] == 1884909.0
    assert verified_results[0].calculated_change_percent == 23.64
    assert warnings == []


def test_quarter_plus_annual_wata_page_three_profit_row_produces_group_annual_metric() -> None:
    table = _make_table(
        3,
        [
            "WATAWALA PLANTATIONS PLC",
            "Condensed Consolidated Income Statement",
            "(all amounts in Sri Lankan Rupees thousands)",
            "Quarter ended 31 March 12 months ended 31 March",
            "2026 2025 Change % 2026 2025 Change %",
            "Revenue 2,174,903 1,878,853 16% 9,442,172 7,800,043 21%",
            "Profit for the period 146,379 412,352 -65% 2,330,446 1,884,909 24%",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_3", 3): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert len(verified_results) == 1
    assert verified_results[0].metric.metric_name == (
        "group_profit_for_the_period_yoy_growth"
    )
    assert verified_results[0].calculated_change_percent == 23.64
    assert warnings == []


def test_company_income_statement_rows_do_not_produce_group_profit_metric() -> None:
    table = _make_table(
        4,
        [
            "Condensed Company Income Statement",
            "Quarter ended 31 March 12 months ended 31 March",
            "2026 2025 Change 2026 2025 Change",
            "Profit for the period 217,326 (76,516) -384% 2,569,593 1,518,270 69%",
            "Equity holders of the parent 217,326 (76,516) -384% 2,569,592 1,518,270 69%",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_4", 4): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert verified_results == []
    assert warnings == []


def test_mixed_page_duplicate_company_income_section_does_not_produce_group_metrics() -> None:
    table = _make_table(
        5,
        [
            "Group Company",
            "31.03.2026 31.03.2025 31.03.2026 31.03.2025",
            "Total Assets 8,600,043 8,713,149 7,589,263 7,686,594",
            "Condensed Statement of Financial Position",
            "Quarter ended 31 March 12 months ended 31 March",
            "2026 2025 Change 2026 2025 Change",
            "Profit for the period 217,326 (76,516) -384% 2,569,593 1,518,270 69%",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_5", 5): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert verified_results == []
    assert warnings == []


def test_mixed_page_primary_balance_section_produces_balance_sheet_metrics_only() -> None:
    table = _make_table(
        5,
        [
            "WATAWALA PLANTATIONS PLC",
            "Group Company",
            "31.03.2026 31.03.2025 31.03.2026 31.03.2025",
            "Assets",
            "Total Assets 8,600,043 8,713,149 7,589,263 7,686,594",
            "Equity and liabilities",
            "Total Equity 3,010,438 3,747,239 2,995,459 3,498,436",
            "Liabilities",
            "Total Liabilities 5,589,606 4,965,910 4,593,804 4,188,158",
            "Condensed Statement of Financial Position",
            "Quarter ended 31 March 12 months ended 31 March",
            "2026 2025 Change 2026 2025 Change",
            "Profit for the period 217,326 (76,516) -384% 2,569,593 1,518,270 69%",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_5", 5): SimpleNamespace(
                statement_type=FinancialStatementType.INCOME_STATEMENT
            )
        },
        metric_entity="group",
    )

    assert [result.metric.metric_name for result in verified_results] == [
        "group_total_assets_growth",
        "group_total_equity_growth",
        "group_total_liabilities_growth",
    ]
    assert [result.calculated_change_percent for result in verified_results] == [
        -1.3,
        -19.66,
        12.56,
    ]
    assert all(
        result.audit_entry.inputs["current"] is not None
        and result.audit_entry.inputs["previous"] is not None
        for result in verified_results
    )
    assert warnings == []


def test_fair_value_note_page_does_not_produce_primary_balance_sheet_metrics() -> None:
    table = _make_table(
        11,
        [
            "Notes to the Condensed Interim Financial Statements",
            "Fair Value Measurement - Group",
            "As at 31 March 2026",
            "Financial assets not measured at fair value",
            "Total financial assets - 1,528,018 - 1,528,018 - 748,439 779,579 1,528,018",
            "Financial liabilities not measured at fair value",
            "Total financial liabilities - 2,163,182 - 2,163,182 - 314,933 1,848,249 2,163,182",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_11", 11): SimpleNamespace(
                statement_type=FinancialStatementType.BALANCE_SHEET
            )
        },
        metric_entity="group",
    )

    assert verified_results == []
    assert warnings == []


def test_primary_balance_sheet_rows_still_produce_balance_sheet_growth_metrics() -> None:
    table = _make_table(
        10,
        [
            "Statement of Financial Position",
            "Total Assets 120 100 20",
            "Total Liabilities 80 70 14.29",
            "Total Equity 40 30 33.33",
        ],
    )

    verified_results, warnings = _build_verified_metric_results_for_tables(
        tables=[table],
        statement_matches_by_key={
            ("pypdf_page_10", 10): SimpleNamespace(
                statement_type=FinancialStatementType.BALANCE_SHEET
            )
        },
        metric_entity="group",
    )

    assert [result.metric.metric_name for result in verified_results] == [
        "group_total_assets_growth",
        "group_total_liabilities_growth",
        "group_total_equity_growth",
    ]
    assert [result.calculated_change_percent for result in verified_results] == [
        20.0,
        14.29,
        33.33,
    ]
    assert warnings == []


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
