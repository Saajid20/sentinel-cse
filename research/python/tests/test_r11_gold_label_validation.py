from __future__ import annotations

import importlib.util
import json
import sys
from itertools import count
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.validation.gold_label import (  # noqa: E402
    GoldLabelValidationStatus,
    validate_gold_label_case,
)

SCRIPT_PATH = PYTHON_ROOT / "scripts" / "r11_validate_gold_label.py"
_TMP_COUNTER = count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    base_dir = PYTHON_ROOT / ".pytest_tmp_gold_label"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{request.node.name}_{next(_TMP_COUNTER)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _make_gold_label() -> dict[str, object]:
    return {
        "schema_version": "r11_gold_label_case_v1",
        "case_id": "fake_case",
        "ticker": "FAKE.N0000",
        "company_name": "Fake Manufacturing PLC",
        "benchmark_level": "CLEAN_SCORECARD",
        "expected_statement_pages": [
            {
                "page_number": 2,
                "statement_type": "INCOME_STATEMENT",
            },
            {
                "page_number": 3,
                "statement_type": "BALANCE_SHEET",
            },
        ],
        "expected_metrics": [
            {
                "metric_name": "group_revenue_growth",
                "source_canonical_item": "revenue",
                "entity_scope": "group",
                "current_value": 125.0,
                "previous_value": 100.0,
                "calculated_value": 25.0,
                "tolerance": 0.01,
                "conflict_expected": False,
                "manual_review_if_missing": True,
            },
            {
                "metric_name": "group_profit_for_the_period_yoy_growth",
                "source_canonical_item": "profit_for_the_period",
                "entity_scope": "group",
                "current_value": 60.0,
                "previous_value": 50.0,
                "calculated_value": 20.0,
                "tolerance": 0.01,
                "conflict_expected": False,
                "manual_review_if_missing": True,
            },
        ],
        "expected_scorecard": {
            "earnings_quality": "IMPROVING",
            "revenue_trend": "IMPROVING",
            "balance_sheet_risk": "LOW",
            "capital_strength": "STRONG",
            "manual_review_required": False,
        },
        "known_gaps": [],
        "manual_review_expected": False,
        "notes": "Fake test gold label.",
    }


def _make_metric(
    metric_name: str,
    *,
    current: float,
    previous: float,
    calculated: float,
    conflict: bool = False,
) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "selected_metric": {
            "metric_name": metric_name,
            "value": calculated,
        },
        "selected_audit_entry": {
            "inputs": {
                "current": current,
                "previous": previous,
            },
            "output": calculated,
        },
        "occurrences": [],
        "conflict": conflict,
        "manual_review_required": conflict,
    }


def _make_analysis() -> dict[str, object]:
    return {
        "schema_version": "r11_deterministic_analysis_v1",
        "statement_classifications": [
            {
                "page_number": 2,
                "table_id": "fake_page_2",
                "statement_type": "INCOME_STATEMENT",
                "confidence": "HIGH",
                "matched_markers": ["INCOME STATEMENT"],
            },
            {
                "page_number": 3,
                "table_id": "fake_page_3",
                "statement_type": "BALANCE_SHEET",
                "confidence": "HIGH",
                "matched_markers": ["TOTAL ASSETS"],
            },
        ],
        "aggregated_metric_results": [
            _make_metric(
                "group_revenue_growth",
                current=125.0,
                previous=100.0,
                calculated=25.0,
            ),
            _make_metric(
                "group_profit_for_the_period_yoy_growth",
                current=60.0,
                previous=50.0,
                calculated=20.0,
            ),
        ],
        "scorecard_build_result": {
            "scorecard": {
                "earnings_quality": "IMPROVING",
                "revenue_trend": "IMPROVING",
                "balance_sheet_risk": "LOW",
                "capital_strength": "STRONG",
                "manual_review_required": False,
            },
            "metric_names_used": [
                "group_revenue_growth",
                "group_profit_for_the_period_yoy_growth",
            ],
            "missing_expected_metrics": [],
            "manual_review_reasons": [],
        },
    }


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "r11_validate_gold_label",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gold_label_validation_passes_when_pages_metrics_and_scorecard_match() -> None:
    result = validate_gold_label_case(
        gold_label=_make_gold_label(),
        analysis_json=_make_analysis(),
    )

    assert result.overall_result is GoldLabelValidationStatus.PASS
    assert result.failed_count == 0
    assert result.manual_review_count == 0
    assert result.passed_count == 9


def test_gold_label_validation_fails_when_statement_page_type_mismatches() -> None:
    analysis = _make_analysis()
    analysis["statement_classifications"][1]["statement_type"] = "EQUITY_STATEMENT"

    result = validate_gold_label_case(
        gold_label=_make_gold_label(),
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.FAIL
    assert any(
        check.check_id == "statement_page_3"
        and check.status is GoldLabelValidationStatus.FAIL
        for check in result.checks
    )


def test_gold_label_validation_fails_when_expected_metric_is_missing() -> None:
    analysis = _make_analysis()
    analysis["aggregated_metric_results"] = analysis["aggregated_metric_results"][:1]

    result = validate_gold_label_case(
        gold_label=_make_gold_label(),
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.FAIL
    assert any(
        check.check_id == "metric_group_profit_for_the_period_yoy_growth"
        and "missing" in check.message
        for check in result.checks
    )


def test_gold_label_validation_fails_when_metric_value_is_outside_tolerance() -> None:
    analysis = _make_analysis()
    analysis["aggregated_metric_results"][0]["selected_metric"]["value"] = 25.5

    result = validate_gold_label_case(
        gold_label=_make_gold_label(),
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.FAIL
    assert any(
        check.check_id == "metric_group_revenue_growth"
        and "calculated_value expected 25.0" in check.message
        for check in result.checks
    )


def test_gold_label_validation_passes_when_metric_value_is_within_tolerance() -> None:
    gold_label = _make_gold_label()
    expected_metrics = gold_label["expected_metrics"]
    expected_metrics[0]["tolerance"] = 0.1
    analysis = _make_analysis()
    analysis["aggregated_metric_results"][0]["selected_metric"]["value"] = 25.05

    result = validate_gold_label_case(
        gold_label=gold_label,
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.PASS


def test_gold_label_validation_fails_when_scorecard_field_mismatches() -> None:
    analysis = _make_analysis()
    analysis["scorecard_build_result"]["scorecard"]["revenue_trend"] = "DETERIORATING"

    result = validate_gold_label_case(
        gold_label=_make_gold_label(),
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.FAIL
    assert any(
        check.check_id == "scorecard_revenue_trend"
        and check.status is GoldLabelValidationStatus.FAIL
        for check in result.checks
    )


def test_gold_label_validation_returns_manual_review_when_manual_review_is_expected() -> None:
    gold_label = _make_gold_label()
    gold_label["expected_scorecard"]["manual_review_required"] = True
    gold_label["manual_review_expected"] = True
    analysis = _make_analysis()
    analysis["scorecard_build_result"]["scorecard"]["manual_review_required"] = True

    result = validate_gold_label_case(
        gold_label=gold_label,
        analysis_json=analysis,
    )

    assert result.overall_result is GoldLabelValidationStatus.MANUAL_REVIEW
    assert any(
        check.check_id == "scorecard_manual_review_required"
        and check.status is GoldLabelValidationStatus.MANUAL_REVIEW
        for check in result.checks
    )


def test_gold_label_validation_cli_writes_output_json_with_fake_files(
    tmp_path: Path,
) -> None:
    script_module = _load_script_module()
    gold_label_path = tmp_path / "gold_label.json"
    analysis_path = tmp_path / "analysis.json"
    output_path = tmp_path / "validation_output.json"
    gold_label_path.write_text(
        json.dumps(_make_gold_label()),
        encoding="utf-8",
        newline="\n",
    )
    analysis_path.write_text(
        json.dumps(_make_analysis()),
        encoding="utf-8",
        newline="\n",
    )

    exit_code = script_module.main(
        [
            "--gold-label",
            str(gold_label_path),
            "--analysis-json",
            str(analysis_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["overall_result"] == "PASS"
    assert payload["passed_count"] == 9
    assert payload["gold_label"] == str(gold_label_path.resolve())
    assert payload["analysis_json"] == str(analysis_path.resolve())


def test_gold_label_validation_uses_no_deepseek_network_or_ocr_code() -> None:
    module_source = (
        (PYTHON_ROOT / "sentinel_research" / "agents" / "r11" / "validation" / "gold_label.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    script_source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    combined_source = module_source + "\n" + script_source

    assert "deepseek" not in combined_source
    assert "requests" not in combined_source
    assert "urllib" not in combined_source
    assert "ocr" not in combined_source
