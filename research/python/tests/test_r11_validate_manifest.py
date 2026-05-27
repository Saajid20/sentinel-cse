from __future__ import annotations

import json
import sys
from itertools import count
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from scripts.r11_validate_manifest import (  # noqa: E402
    build_manifest_report_payload,
    main,
    resolve_case_analysis_json_path,
    run_manifest_case,
)
from sentinel_research.agents.r11.validation import (  # noqa: E402
    R11ValidationCase,
    R11ValidationManifest,
)

_TMP_COUNTER = count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    base_dir = PYTHON_ROOT / ".pytest_tmp_validate_manifest_runner"
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
                    "inputs": {"current": 120.0, "previous": 100.0},
                    "output": 20.0,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [],
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
                    "source_traces": [],
                    "notes": "selected metric",
                },
                "selected_audit_entry": {
                    "tool_name": "r11_calculation_toolbox",
                    "tool_version": None,
                    "operation": "calculate_yoy_growth",
                    "metric_name": "group_profit_for_the_period_yoy_growth",
                    "formula": "(current - previous) / abs(previous) * 100",
                    "inputs": {"current": 120.0, "previous": 100.0},
                    "output": 20.0,
                    "verified": True,
                    "generated_at": "2026-05-26T12:00:00Z",
                    "source_traces": [],
                    "notes": "selected audit",
                },
                "occurrences": [
                    {
                        "metric_name": "group_profit_for_the_period_yoy_growth",
                        "calculated_change_percent": 19.8,
                        "reported_change_percent": 20.0,
                        "difference_percent_points": -0.2,
                        "matches_reported": False,
                        "source_traces": [],
                        "audit_entry": {
                            "tool_name": "r11_calculation_toolbox",
                            "tool_version": None,
                            "operation": "calculate_yoy_growth",
                            "metric_name": "group_profit_for_the_period_yoy_growth",
                            "formula": "(current - previous) / abs(previous) * 100",
                            "inputs": {"current": 120.0, "previous": 100.0},
                            "output": 20.0,
                            "verified": True,
                            "generated_at": "2026-05-26T12:00:00Z",
                            "source_traces": [],
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


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")


def _make_case(
    analysis_json_path: str,
    **overrides: object,
) -> dict[str, object]:
    payload = {
        "case_id": "comb_q1_2026_known_good",
        "ticker": "COMB.N0000",
        "company_name": "Commercial Bank of Ceylon PLC",
        "description": "Known-good deterministic COMB validation case.",
        "analysis_json_path": analysis_json_path,
        "expected_pages": [
            {"page_number": 5, "statement_type": "INCOME_STATEMENT"},
            {"page_number": 7, "statement_type": "BALANCE_SHEET"},
        ],
        "min_verified_metrics": 1,
        "min_aggregated_metrics": 1,
        "expect_manual_review": False,
        "require_scorecard": True,
        "require_no_conflicts": True,
        "notes": "local-only runtime path",
    }
    payload.update(overrides)
    return payload


def _write_manifest(tmp_path: Path, filename: str, cases: list[dict[str, object]]) -> Path:
    manifest = R11ValidationManifest(
        cases=[R11ValidationCase.model_validate(case) for case in cases],
        notes="multi-case manifest test",
    )
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8", newline="\n")
    return path


def test_manifest_runner_loads_one_valid_case_and_passes(tmp_path: Path) -> None:
    analysis_path = tmp_path / "analysis.json"
    _write_payload(analysis_path, _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("analysis.json")],
    )

    exit_code = main(["--manifest", str(manifest_path)])

    assert exit_code == 0


def test_multiple_passing_cases_produce_cases_passed_count(tmp_path: Path) -> None:
    _write_payload(tmp_path / "analysis_a.json", _make_analysis_payload())
    _write_payload(tmp_path / "analysis_b.json", _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [
            _make_case("analysis_a.json", case_id="case_a"),
            _make_case("analysis_b.json", case_id="case_b"),
        ],
    )

    manifest = R11ValidationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    case_results = [
        run_manifest_case(manifest_path, case)
        for case in manifest.cases
    ]
    report = build_manifest_report_payload(manifest_path, case_results)

    assert report["cases_passed"] == 2
    assert report["cases_failed"] == 0


def test_missing_analysis_json_causes_fail_user_error(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("missing_analysis.json")],
    )

    exit_code = main(["--manifest", str(manifest_path)])

    assert exit_code == 2


def test_one_failing_case_gives_exit_report_status_fail(tmp_path: Path) -> None:
    _write_payload(tmp_path / "analysis.json", _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("analysis.json", min_verified_metrics=2)],
    )

    manifest = R11ValidationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    case_result = run_manifest_case(manifest_path, manifest.cases[0])

    assert case_result.overall_result == "FAIL"
    assert main(["--manifest", str(manifest_path)]) == 2


def test_conflict_manual_review_case_gives_manual_review_status(tmp_path: Path) -> None:
    payload = _make_analysis_payload()
    aggregated = payload["aggregated_metric_results"]
    assert isinstance(aggregated, list)
    aggregated[0]["conflict"] = True
    aggregated[0]["manual_review_required"] = True
    aggregated[0]["conflict_reason"] = "duplicate results disagree"
    _write_payload(tmp_path / "analysis.json", payload)
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("analysis.json")],
    )

    manifest = R11ValidationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    case_result = run_manifest_case(manifest_path, manifest.cases[0])

    assert case_result.overall_result == "MANUAL_REVIEW"
    assert main(["--manifest", str(manifest_path)]) == 1


def test_output_json_report_is_written_and_serializable(tmp_path: Path) -> None:
    _write_payload(tmp_path / "analysis.json", _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("analysis.json")],
    )
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output-json",
            str(output_path),
        ]
    )
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["schema_version"] == "r11_validation_manifest_report_v1"
    assert report["cases_total"] == 1


def test_relative_analysis_json_path_resolves_relative_to_manifest_parent(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    analysis_dir = manifest_dir / "relative"
    analysis_path = analysis_dir / "analysis.json"
    _write_payload(analysis_path, _make_analysis_payload())
    manifest_path = _write_manifest(
        manifest_dir,
        "manifest.json",
        [_make_case("relative/analysis.json")],
    )
    case = R11ValidationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    ).cases[0]

    resolved = resolve_case_analysis_json_path(manifest_path, case)

    assert resolved == analysis_path.resolve()


def test_base_dir_overrides_relative_analysis_path_resolution(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    base_dir = tmp_path / "base"
    analysis_path = base_dir / "shared" / "analysis.json"
    _write_payload(analysis_path, _make_analysis_payload())
    manifest_path = _write_manifest(
        manifest_dir,
        "manifest.json",
        [_make_case("shared/analysis.json")],
    )
    case = R11ValidationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    ).cases[0]

    resolved = resolve_case_analysis_json_path(
        manifest_path,
        case,
        base_dir=base_dir,
    )

    assert resolved == analysis_path.resolve()


def test_stop_on_fail_stops_after_first_failing_case(tmp_path: Path) -> None:
    _write_payload(tmp_path / "analysis_fail.json", _make_analysis_payload())
    _write_payload(tmp_path / "analysis_pass.json", _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [
            _make_case("analysis_fail.json", case_id="case_fail", min_verified_metrics=2),
            _make_case("analysis_pass.json", case_id="case_pass"),
        ],
    )
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "--manifest",
            str(manifest_path),
            "--stop-on-fail",
            "--output-json",
            str(output_path),
        ]
    )
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert report["cases_total"] == 1
    assert len(report["case_results"]) == 1
    assert report["case_results"][0]["case_id"] == "case_fail"


def test_no_test_calls_deepseek_or_network(tmp_path: Path) -> None:
    _write_payload(tmp_path / "analysis.json", _make_analysis_payload())
    manifest_path = _write_manifest(
        tmp_path,
        "manifest.json",
        [_make_case("analysis.json")],
    )

    exit_code = main(["--manifest", str(manifest_path)])

    assert exit_code == 0
