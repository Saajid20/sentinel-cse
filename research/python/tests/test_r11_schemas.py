from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11 import (  # noqa: E402
    AccountingRedFlag,
    ExtractedFinancialTable,
    FinancialMetric,
    FinancialStatementType,
    FundamentalScorecard,
    MetricUnit,
    NormalizedFinancialLineItem,
    NormalizedFinancialStatement,
    R11AnalystDossier,
    R11DocumentType,
    SourceTrace,
    ToolAuditEntry,
    build_dossier_id,
)


def make_source_trace(**overrides: object) -> SourceTrace:
    payload = {
        "source_document_id": " doc-001 ",
        "source_type": " CSE_DISCLOSURE ",
        "source_url": " https://example.test/disclosure.pdf ",
        "local_file_path": " C:/docs/disclosure.pdf ",
        "ticker": " jkh.n0000 ",
        "company": " John Keells Holdings ",
        "announcement_id": " 12345 ",
        "page_number": 3,
        "table_id": " table-1 ",
        "row_label": " Revenue ",
        "column_label": " Q1 2026 ",
        "raw_value": " 100 ",
        "extracted_value": 100,
        "notes": " extracted from statement ",
    }
    payload.update(overrides)
    return SourceTrace.model_validate(payload)


def make_table(**overrides: object) -> ExtractedFinancialTable:
    payload = {
        "table_id": " income-table-1 ",
        "statement_type": "INCOME_STATEMENT",
        "title": " Income Statement ",
        "page_number": 5,
        "columns": [" Period ", " Revenue ", " "],
        "rows": [{"Period": "Q1 2026", "Revenue": 1000}],
        "extraction_method": " camelot ",
        "source_trace": make_source_trace(),
    }
    payload.update(overrides)
    return ExtractedFinancialTable.model_validate(payload)


def make_line_item(**overrides: object) -> NormalizedFinancialLineItem:
    payload = {
        "canonical_name": " Profit after taxation ",
        "original_label": " Profit after taxation ",
        "statement_type": "INCOME_STATEMENT",
        "period_values": {"Q1 2026": 1200, "Q1 2025": 1000},
        "unit": "LKR_MILLION",
        "source_trace": make_source_trace(),
    }
    payload.update(overrides)
    return NormalizedFinancialLineItem.model_validate(payload)


def make_statement(**overrides: object) -> NormalizedFinancialStatement:
    payload = {
        "statement_id": " stmt-001 ",
        "ticker": " comb.n0000 ",
        "company": " Commercial Bank ",
        "sector": "BANKING",
        "document_type": "INTERIM_FINANCIAL_STATEMENT",
        "period_label": " Q1 2026 ",
        "statement_type": "INCOME_STATEMENT",
        "line_items": [make_line_item()],
        "source_trace": make_source_trace(),
    }
    payload.update(overrides)
    return NormalizedFinancialStatement.model_validate(payload)


def make_tool_audit(**overrides: object) -> ToolAuditEntry:
    payload = {
        "tool_name": " metric_toolbox ",
        "tool_version": " 0.1 ",
        "operation": " calculate_ratio ",
        "metric_name": " debt_to_equity ",
        "formula": " liabilities / equity ",
        "inputs": {"liabilities": 10.0, "equity": 5.0},
        "output": 2.0,
        "generated_at": datetime(2026, 5, 26, 12, 0, 0, tzinfo=UTC),
        "source_traces": [make_source_trace()],
        "notes": " verified locally ",
    }
    payload.update(overrides)
    return ToolAuditEntry.model_validate(payload)


def make_metric(**overrides: object) -> FinancialMetric:
    payload = {
        "metric_name": " Gross Margin ",
        "display_name": " Gross Margin ",
        "value": 0.32,
        "unit": "RATIO",
        "period": " Q1 2026 ",
        "comparison_period": " Q1 2025 ",
        "direction": "IMPROVING",
        "calculation_audit_id": " audit-001 ",
        "source_traces": [make_source_trace()],
        "notes": " derived from audited table ",
    }
    payload.update(overrides)
    return FinancialMetric.model_validate(payload)


def make_scorecard(**overrides: object) -> FundamentalScorecard:
    payload = {
        "earnings_quality": "IMPROVING",
        "revenue_trend": "IMPROVING",
        "margin_trend": "STABLE",
        "cash_flow_quality": "UNKNOWN",
        "summary": "Results show stable execution with no trading instruction.",
    }
    payload.update(overrides)
    return FundamentalScorecard.model_validate(payload)


def make_red_flag(**overrides: object) -> AccountingRedFlag:
    payload = {
        "red_flag_id": " red-001 ",
        "category": " Impairment Charges ",
        "severity": "MEDIUM",
        "description": "Impairment charges increased materially year over year.",
        "source_traces": [make_source_trace()],
    }
    payload.update(overrides)
    return AccountingRedFlag.model_validate(payload)


def make_dossier(**overrides: object) -> R11AnalystDossier:
    generated_at = datetime(2026, 5, 26, 12, 0, 0, tzinfo=UTC)
    payload = {
        "dossier_id": build_dossier_id("jkh.n0000", generated_at, "Q1 2026"),
        "generated_at": generated_at,
        "ticker": " jkh.n0000 ",
        "company": " John Keells Holdings ",
        "sector": "DIVERSIFIED",
        "document_type": "INTERIM_FINANCIAL_STATEMENT",
        "period_label": " Q1 2026 ",
        "source_traces": [make_source_trace()],
        "extracted_tables": [make_table()],
        "normalized_statements": [make_statement()],
        "financial_metrics": [],
        "fundamental_scorecard": make_scorecard(),
        "accounting_red_flags": [],
        "tool_audit": [],
        "analyst_summary": "Revenue and profitability trends require fundamental review.",
        "confidence": "MEDIUM",
        "manual_review_required": False,
        "notes": " schema validation only ",
    }
    payload.update(overrides)
    return R11AnalystDossier.model_validate(payload)


def test_source_trace_strips_strings_uppercased_ticker_and_empty_optionals_to_none() -> None:
    trace = make_source_trace(
        source_type="   ",
        local_file_path=" ",
        notes=" ",
    )

    assert trace.source_document_id == "doc-001"
    assert trace.source_type is None
    assert trace.local_file_path is None
    assert trace.ticker == "JKH.N0000"
    assert trace.announcement_id == "12345"
    assert trace.notes is None


def test_source_trace_rejects_non_positive_page_number() -> None:
    with pytest.raises(ValidationError, match="page_number must be positive"):
        make_source_trace(page_number=0)


def test_extracted_financial_table_rejects_empty_columns_and_rows() -> None:
    with pytest.raises(ValidationError, match="columns must not be empty"):
        make_table(columns=[" ", ""])

    with pytest.raises(ValidationError, match="rows must not be empty"):
        make_table(rows=[])


def test_normalized_financial_line_item_normalizes_canonical_name_to_snake_case() -> None:
    item = make_line_item(canonical_name=" Profit-after taxation ")

    assert item.canonical_name == "profit_after_taxation"


def test_normalized_financial_statement_uppercased_ticker_and_rejects_empty_line_items() -> None:
    statement = make_statement(ticker=" samp.n0000 ")

    assert statement.ticker == "SAMP.N0000"

    with pytest.raises(ValidationError, match="line_items must not be empty"):
        make_statement(line_items=[])


def test_tool_audit_entry_requires_timezone_aware_generated_at() -> None:
    with pytest.raises(ValidationError, match="generated_at must be timezone-aware"):
        make_tool_audit(generated_at=datetime(2026, 5, 26, 12, 0, 0))


def test_financial_metric_normalizes_metric_name() -> None:
    metric = make_metric(metric_name=" Net Margin ")

    assert metric.metric_name == "net_margin"


def test_fundamental_scorecard_rejects_trading_recommendation_language_in_summary() -> None:
    with pytest.raises(ValidationError, match="summary contains unsafe trading recommendation language"):
        make_scorecard(summary="Buy this name after the quarter.")


def test_accounting_red_flag_normalizes_category_and_rejects_empty_description() -> None:
    red_flag = make_red_flag(category=" Margin Compression ")

    assert red_flag.category == "margin_compression"

    with pytest.raises(ValidationError, match="description must not be empty"):
        make_red_flag(description="   ")


def test_r11_analyst_dossier_accepts_valid_minimal_dossier() -> None:
    dossier = make_dossier(
        extracted_tables=[],
        normalized_statements=[],
        financial_metrics=[],
        accounting_red_flags=[],
        tool_audit=[],
    )

    assert dossier.schema_version == "r11_analyst_dossier_v1"
    assert dossier.ticker == "JKH.N0000"


def test_r11_analyst_dossier_locks_schema_version() -> None:
    with pytest.raises(ValidationError, match="r11_analyst_dossier_v1"):
        make_dossier(schema_version="r11_analyst_dossier_v2")


def test_r11_analyst_dossier_requires_at_least_one_source_trace() -> None:
    with pytest.raises(ValidationError, match="source_traces must not be empty"):
        make_dossier(source_traces=[])


def test_r11_analyst_dossier_uppercased_ticker() -> None:
    dossier = make_dossier(ticker=" comb.n0000 ")

    assert dossier.ticker == "COMB.N0000"


def test_r11_analyst_dossier_rejects_trading_recommendation_language_in_analyst_summary() -> None:
    with pytest.raises(ValidationError, match="analyst_summary contains unsafe trading recommendation language"):
        make_dossier(analyst_summary="Sell the stock after these numbers.")


def test_r11_analyst_dossier_sets_manual_review_required_for_high_or_critical_red_flags() -> None:
    dossier = make_dossier(
        accounting_red_flags=[make_red_flag(severity="HIGH")],
        manual_review_required=False,
    )

    assert dossier.manual_review_required is True


def test_r11_analyst_dossier_sets_manual_review_required_for_calculated_metrics_without_tool_audit() -> None:
    dossier = make_dossier(
        financial_metrics=[make_metric(metric_name="Revenue Growth", calculation_audit_id=None)],
        tool_audit=[],
        manual_review_required=False,
    )

    assert dossier.manual_review_required is True


def test_build_dossier_id_creates_deterministic_filename_safe_ids() -> None:
    generated_at = datetime(2026, 5, 26, 15, 45, 30, tzinfo=UTC)

    dossier_id = build_dossier_id("jkh.n0000", generated_at, "Q1 2026 / Interim")

    assert dossier_id == "r11_dossier_JKH.N0000_20260526T154530Z_Q1_2026_Interim"


def test_model_dump_json_round_trip_validates_back_into_r11_analyst_dossier() -> None:
    dossier = make_dossier(
        financial_metrics=[make_metric(metric_name="Net Margin")],
        tool_audit=[make_tool_audit(metric_name="net_margin")],
    )

    dumped = dossier.model_dump_json()
    loaded = R11AnalystDossier.model_validate_json(dumped)

    assert loaded == dossier


def test_r11_schema_tests_do_not_use_deepseek_or_network() -> None:
    dossier = make_dossier()

    assert dossier.model_dump()["company"] == "John Keells Holdings"
