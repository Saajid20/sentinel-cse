from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from scripts.r11_generate_dossier_from_analysis import (  # noqa: E402
    _extract_dossier_components,
    _load_analysis_payload,
    _statement_classifications_to_source_traces,
)


def _make_analysis_payload() -> dict[str, object]:
    return {
        "schema_version": "r11_deterministic_analysis_v1",
        "pdf_path": "C:/tmp/comb_q1_2026.pdf",
        "extraction_method": "pypdf_baseline",
        "pages_extracted": [5, 6, 7, 8],
        "pages_matched": [5, 6, 7, 8],
        "pages_shown": [5, 6, 7, 8],
        "active_filters": ["start_page>=5", "end_page<=8"],
        "statement_classifications": [
            {
                "page_number": 5,
                "table_id": "pypdf_page_5",
                "statement_type": "INCOME_STATEMENT",
                "confidence": "HIGH",
                "matched_markers": ["GROSS INCOME", "PROFIT FOR THE PERIOD"],
                "notes": None,
            }
        ],
        "verified_metric_results": [
            {
                "metric": {
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "display_name": "Group Profit For The Period YoY Growth",
                    "value": 19.8,
                    "unit": "PERCENT",
                    "period": "current",
                    "comparison_period": "previous",
                    "direction": "IMPROVING",
                    "calculation_audit_id": "audit_group_profit_for_the_period_yoy_growth",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Commercial Bank of Ceylon PLC",
                            "raw_value": "raw row",
                            "notes": "metric builder test",
                        }
                    ],
                    "notes": "Reported change matched calculated change within 0.05 percentage points.",
                },
                "audit_entry": {
                    "tool_name": "r11_calculation_toolbox",
                    "tool_version": None,
                    "operation": "calculate_yoy_growth",
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "formula": "(current - previous) / abs(previous) * 100",
                    "inputs": {
                        "current": 17936712.0,
                        "previous": 14972114.0,
                        "reported_change_percent": 19.8,
                    },
                    "output": 19.8,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Commercial Bank of Ceylon PLC",
                            "raw_value": "raw row",
                            "notes": "metric builder test",
                        }
                    ],
                    "notes": "Reported change matched calculated change within 0.05 percentage points.",
                },
                "reported_change_percent": 19.8,
                "calculated_change_percent": 19.8,
                "difference_percent_points": 0.0,
                "matches_reported": True,
                "tolerance_percent_points": 0.05,
                "notes": "Reported change matched calculated change within 0.05 percentage points.",
            }
        ],
        "aggregated_metric_results": [
            {
                "metric_name": "group_profit_for_the_period_yoy_growth",
                "selected_metric": {
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "display_name": "Group Profit For The Period YoY Growth",
                    "value": 19.8,
                    "unit": "PERCENT",
                    "period": "current",
                    "comparison_period": "previous",
                    "direction": "IMPROVING",
                    "calculation_audit_id": "audit_group_profit_for_the_period_yoy_growth",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Commercial Bank of Ceylon PLC",
                            "raw_value": "raw row",
                            "notes": "metric builder test",
                        }
                    ],
                    "notes": "selected metric",
                },
                "selected_audit_entry": {
                    "tool_name": "r11_calculation_toolbox",
                    "tool_version": None,
                    "operation": "calculate_yoy_growth",
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "formula": "(current - previous) / abs(previous) * 100",
                    "inputs": {
                        "current": 17936712.0,
                        "previous": 14972114.0,
                        "reported_change_percent": 19.8,
                    },
                    "output": 19.8,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Commercial Bank of Ceylon PLC",
                            "raw_value": "raw row",
                            "notes": "metric builder test",
                        }
                    ],
                    "notes": "selected audit",
                },
                "occurrences": [
                    {
                        "metric_name": "group_profit_for_the_period_yoy_growth",
                        "calculated_change_percent": 19.8,
                        "reported_change_percent": 19.8,
                        "difference_percent_points": 0.0,
                        "matches_reported": True,
                        "source_traces": [
                            {
                                "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                                "page_number": 5,
                                "table_id": "pypdf_page_5",
                                "row_label": "Profit for the period",
                                "company": "Commercial Bank of Ceylon PLC",
                                "raw_value": "raw row",
                                "notes": "metric builder test",
                            }
                        ],
                        "audit_entry": {
                            "tool_name": "r11_calculation_toolbox",
                            "tool_version": None,
                            "operation": "calculate_yoy_growth",
                            "metric_name": "group_profit_for_the_period_yoy_growth",
                            "formula": "(current - previous) / abs(previous) * 100",
                            "inputs": {
                                "current": 17936712.0,
                                "previous": 14972114.0,
                                "reported_change_percent": 19.8,
                            },
                            "output": 19.8,
                            "verified": True,
                            "generated_at": "2026-05-26T12:00:00Z",
                            "source_traces": [
                                {
                                    "local_file_path": "C:/tmp/comb_q1_2026.pdf",
                                    "page_number": 5,
                                    "table_id": "pypdf_page_5",
                                    "row_label": "Profit for the period",
                                    "company": "Commercial Bank of Ceylon PLC",
                                    "raw_value": "raw row",
                                    "notes": "metric builder test",
                                }
                            ],
                            "notes": "selected audit",
                        },
                        "notes": "occurrence",
                    }
                ],
                "occurrence_count": 1,
                "conflict": False,
                "manual_review_required": False,
                "conflict_reason": None,
                "selected_reason": "Selected preferred occurrence with reported-match verification.",
                "notes": "Aggregated 1 duplicate occurrences without conflict.",
            }
        ],
        "scorecard_build_result": {
            "scorecard": {
                "earnings_quality": "IMPROVING",
                "revenue_trend": "IMPROVING",
                "margin_trend": "MIXED",
                "balance_sheet_risk": "MEDIUM",
                "cash_flow_quality": "UNKNOWN",
                "capital_strength": "MEDIUM",
                "accounting_risk": None,
                "manual_review_required": False,
                "summary": "Deterministic R11 scorecard built from verified financial statement metrics.",
            },
            "metric_names_used": ["group_profit_for_the_period_yoy_growth"],
            "missing_expected_metrics": [],
            "manual_review_reasons": [],
            "notes": "scorecard note",
        },
        "scorecard_build_error": None,
        "generated_at": "2026-05-26T12:00:00Z",
        "notes": ["Deterministic R11 analysis artifact built from the local manual inspection pipeline."],
    }


def _write_payload_in_workspace(filename: str) -> Path:
    output_dir = PYTHON_ROOT / ".pytest_tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(_make_analysis_payload()), encoding="utf-8", newline="\n")
    return path


def test_load_analysis_payload_validates_schema_version_and_returns_object() -> None:
    path = _write_payload_in_workspace("r11_generate_dossier_from_analysis_payload.json")

    payload = _load_analysis_payload(path)

    assert payload["schema_version"] == "r11_deterministic_analysis_v1"


def test_statement_classifications_to_source_traces_builds_page_traces() -> None:
    traces = _statement_classifications_to_source_traces(_make_analysis_payload())

    assert len(traces) == 1
    assert traces[0].page_number == 5
    assert traces[0].table_id == "pypdf_page_5"


def test_extract_dossier_components_reconstructs_scorecard_metrics_audits_and_traces() -> None:
    (
        scorecard_result,
        aggregated_metrics,
        financial_metrics,
        tool_audit_entries,
        source_traces,
    ) = _extract_dossier_components(_make_analysis_payload())

    assert scorecard_result.scorecard.earnings_quality.value == "IMPROVING"
    assert len(aggregated_metrics) == 1
    assert financial_metrics[0].metric_name == "group_profit_for_the_period_yoy_growth"
    assert tool_audit_entries[0].metric_name == "group_profit_for_the_period_yoy_growth"
    assert source_traces[0].page_number == 5


def test_no_test_calls_deepseek_or_network() -> None:
    path = _write_payload_in_workspace("r11_generate_dossier_from_analysis_no_network.json")

    payload = _load_analysis_payload(path)

    assert payload["pdf_path"] == "C:/tmp/comb_q1_2026.pdf"
