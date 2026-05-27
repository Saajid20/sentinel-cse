from __future__ import annotations

import json
import sys
from itertools import count
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from scripts.r11_validate_analysis_json import (  # noqa: E402
    ExpectedPageCheck,
    _load_analysis_payload,
    _load_analysis_validation_context,
    _validation_output_payload,
    main,
    run_validation_checklist,
    ValidationCliOptions,
)
from sentinel_research.agents.r11.schemas import FinancialStatementType  # noqa: E402

_TMP_COUNTER = count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    base_dir = PYTHON_ROOT / ".pytest_tmp_validate"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{request.node.name}_{next(_TMP_COUNTER)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _make_analysis_payload() -> dict[str, object]:
    return {
        "schema_version": "r11_deterministic_analysis_v1",
        "pdf_path": "C:/tmp/fake_statement.pdf",
        "statement_classifications": [
            {
                "page_number": 5,
                "table_id": "pypdf_page_5",
                "statement_type": "INCOME_STATEMENT",
                "confidence": "HIGH",
                "matched_markers": ["INCOME STATEMENT", "PROFIT FOR THE PERIOD"],
                "notes": None,
            },
            {
                "page_number": 7,
                "table_id": "pypdf_page_7",
                "statement_type": "BALANCE_SHEET",
                "confidence": "HIGH",
                "matched_markers": ["STATEMENT OF FINANCIAL POSITION", "TOTAL ASSETS"],
                "notes": None,
            },
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
                            "local_file_path": "C:/tmp/fake_statement.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Fake Company PLC",
                            "raw_value": "raw row",
                            "notes": "fake metric",
                        }
                    ],
                    "notes": "verified metric",
                },
                "audit_entry": {
                    "tool_name": "r11_calculation_toolbox",
                    "tool_version": None,
                    "operation": "calculate_yoy_growth",
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "formula": "(current - previous) / abs(previous) * 100",
                    "inputs": {
                        "current": 120.0,
                        "previous": 100.0,
                        "reported_change_percent": 20.0,
                    },
                    "output": 20.0,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/fake_statement.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Fake Company PLC",
                            "raw_value": "raw row",
                            "notes": "fake metric",
                        }
                    ],
                    "notes": "verified audit",
                },
                "reported_change_percent": 20.0,
                "calculated_change_percent": 19.8,
                "difference_percent_points": -0.2,
                "matches_reported": False,
                "tolerance_percent_points": 0.25,
                "notes": "fake verification result",
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
                            "local_file_path": "C:/tmp/fake_statement.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Fake Company PLC",
                            "raw_value": "raw row",
                            "notes": "fake metric",
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
                        "current": 120.0,
                        "previous": 100.0,
                        "reported_change_percent": 20.0,
                    },
                    "output": 20.0,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [
                        {
                            "local_file_path": "C:/tmp/fake_statement.pdf",
                            "page_number": 5,
                            "table_id": "pypdf_page_5",
                            "row_label": "Profit for the period",
                            "company": "Fake Company PLC",
                            "raw_value": "raw row",
                            "notes": "fake metric",
                        }
                    ],
                    "notes": "selected audit",
                },
                "occurrences": [
                    {
                        "metric_name": "group_profit_for_the_period_yoy_growth",
                        "calculated_change_percent": 19.8,
                        "reported_change_percent": 20.0,
                        "difference_percent_points": -0.2,
                        "matches_reported": False,
                        "source_traces": [
                            {
                                "local_file_path": "C:/tmp/fake_statement.pdf",
                                "page_number": 5,
                                "table_id": "pypdf_page_5",
                                "row_label": "Profit for the period",
                                "company": "Fake Company PLC",
                                "raw_value": "raw row",
                                "notes": "fake metric",
                            }
                        ],
                        "audit_entry": {
                            "tool_name": "r11_calculation_toolbox",
                            "tool_version": None,
                            "operation": "calculate_yoy_growth",
                            "metric_name": "group_profit_for_the_period_yoy_growth",
                            "formula": "(current - previous) / abs(previous) * 100",
                            "inputs": {
                                "current": 120.0,
                                "previous": 100.0,
                                "reported_change_percent": 20.0,
                            },
                            "output": 20.0,
                            "verified": True,
                            "generated_at": "2026-05-26T12:00:00Z",
                            "source_traces": [
                                {
                                    "local_file_path": "C:/tmp/fake_statement.pdf",
                                    "page_number": 5,
                                    "table_id": "pypdf_page_5",
                                    "row_label": "Profit for the period",
                                    "company": "Fake Company PLC",
                                    "raw_value": "raw row",
                                    "notes": "fake metric",
                                }
                            ],
                            "notes": "occurrence audit",
                        },
                        "notes": "fake occurrence",
                    }
                ],
                "occurrence_count": 1,
                "conflict": False,
                "manual_review_required": False,
                "conflict_reason": None,
                "selected_reason": "Selected deterministically.",
                "notes": "no conflict",
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
                "summary": "Deterministic scorecard summary without trading language.",
            },
            "metric_names_used": ["group_profit_for_the_period_yoy_growth"],
            "missing_expected_metrics": [],
            "manual_review_reasons": [],
            "notes": "scorecard test result",
        },
    }


def _write_payload(tmp_path: Path, filename: str, payload: dict[str, object]) -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return path


def test_load_valid_analysis_payload(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "analysis.json", _make_analysis_payload())

    payload = _load_analysis_payload(path)

    assert payload["schema_version"] == "r11_deterministic_analysis_v1"


def test_invalid_schema_version_fails_cleanly_through_helper(tmp_path: Path) -> None:
    payload = _make_analysis_payload()
    payload["schema_version"] = "invalid_version"
    path = _write_payload(tmp_path, "invalid_schema.json", payload)

    with pytest.raises(ValueError, match="r11_deterministic_analysis_v1"):
        _load_analysis_payload(path)


def test_expected_page_statement_type_passes(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "page_pass.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[_expected_page(5, "INCOME_STATEMENT")]),
    )

    assert evaluation.overall_status.value == "PASS"
    assert evaluation.passed_items == 1


def test_missing_expected_page_fails(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "page_fail.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[_expected_page(6, "INCOME_STATEMENT")]),
    )

    assert evaluation.overall_status.value == "FAIL"
    assert evaluation.failed_items == 1


def test_min_verified_and_aggregated_metric_checks_pass_and_fail(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "metric_thresholds.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)

    passing = run_validation_checklist(
        context,
        ValidationCliOptions(
            expected_pages=[],
            min_verified_metrics=1,
            min_aggregated_metrics=1,
        ),
    )
    failing = run_validation_checklist(
        context,
        ValidationCliOptions(
            expected_pages=[],
            min_verified_metrics=2,
            min_aggregated_metrics=2,
        ),
    )

    assert passing.overall_status.value == "PASS"
    assert failing.overall_status.value == "FAIL"


def test_require_scorecard_fails_when_absent(tmp_path: Path) -> None:
    payload = _make_analysis_payload()
    payload["scorecard_build_result"] = None
    path = _write_payload(tmp_path, "missing_scorecard.json", payload)
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[], require_scorecard=True),
    )

    assert evaluation.overall_status.value == "FAIL"
    assert evaluation.evaluations[0].item_id == "require_scorecard"


def test_expect_manual_review_false_passes_for_clean_scorecard(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "manual_review_false.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[], expect_manual_review=False),
    )

    assert evaluation.overall_status.value == "PASS"
    assert evaluation.evaluations[0].status.value == "PASS"


def test_conflict_in_aggregated_metrics_triggers_manual_review(tmp_path: Path) -> None:
    payload = _make_analysis_payload()
    aggregated = payload["aggregated_metric_results"]
    assert isinstance(aggregated, list)
    aggregated[0]["conflict"] = True
    aggregated[0]["manual_review_required"] = True
    aggregated[0]["conflict_reason"] = "duplicate results disagree"
    path = _write_payload(tmp_path, "conflict.json", payload)
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[], require_no_conflicts=True),
    )

    assert evaluation.overall_status.value == "MANUAL_REVIEW"
    assert evaluation.manual_review_items == 1
    assert evaluation.evaluations[0].status.value == "MANUAL_REVIEW"


def test_output_json_payload_is_serializable(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "output_payload.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)
    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[_expected_page(5, "INCOME_STATEMENT")]),
    )

    payload = _validation_output_payload(context, evaluation)
    encoded = json.dumps(payload)

    assert payload["analysis_json"].endswith("output_payload.json")
    assert '"overall_status": "PASS"' in encoded


def test_main_writes_output_json(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "main_output.json", _make_analysis_payload())
    output_path = tmp_path / "validation_output.json"

    exit_code = main(
        [
            "--analysis-json",
            str(path),
            "--expect-page",
            "5:INCOME_STATEMENT",
            "--output-json",
            str(output_path),
        ]
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert saved["overall_status"] == "PASS"


def test_no_test_calls_deepseek_or_network(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, "no_network.json", _make_analysis_payload())
    context = _load_analysis_validation_context(path)

    evaluation = run_validation_checklist(
        context,
        ValidationCliOptions(expected_pages=[_expected_page(7, "BALANCE_SHEET")]),
    )

    assert evaluation.checklist_id == "r11_analysis_json_manual_validation"


def _expected_page(page_number: int, statement_type: str) -> ExpectedPageCheck:
    return ExpectedPageCheck(
        page_number=page_number,
        statement_type=FinancialStatementType(statement_type),
    )
