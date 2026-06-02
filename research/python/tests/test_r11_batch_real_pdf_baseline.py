from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from itertools import count
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.ingestion import CseFinancialReport  # noqa: E402

SCRIPT_PATH = PYTHON_ROOT / "scripts" / "r11_batch_real_pdf_baseline.py"
_TMP_COUNTER = count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    base_dir = PYTHON_ROOT / ".pytest_tmp_r11_batch"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{request.node.name}_{next(_TMP_COUNTER)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def script_module():
    spec = importlib.util.spec_from_file_location(
        "r11_batch_real_pdf_baseline",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_report(
    *,
    report_id: int,
    symbol: str,
    company: str,
    file_text: str,
    manual_date_ms: int,
    path: str,
) -> CseFinancialReport:
    return CseFinancialReport.model_validate(
        {
            "id": report_id,
            "path": path,
            "manualDate": manual_date_ms,
            "uploadedDate": "27 May 2026 05:39:02 PM",
            "fileText": file_text,
            "name": company,
            "symbol": symbol,
            "logoUrl": "upload_logo/example.gif",
            "authorizedDate": "27 May 2026 06:11:25 PM",
        }
    )


def _write_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    return config_path


def _make_analysis_payload() -> dict[str, object]:
    return {
        "schema_version": "r11_deterministic_analysis_v1",
        "pdf_path": "C:/tmp/fake_statement.pdf",
        "statement_classifications": [
            {
                "page_number": 2,
                "table_id": "pypdf_page_2",
                "statement_type": "INCOME_STATEMENT",
                "confidence": "HIGH",
                "matched_markers": ["INCOME STATEMENT"],
                "notes": None,
            },
            {
                "page_number": 4,
                "table_id": "pypdf_page_4",
                "statement_type": "BALANCE_SHEET",
                "confidence": "HIGH",
                "matched_markers": ["TOTAL ASSETS"],
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
                    "source_traces": [],
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
                "revenue_trend": "UNKNOWN",
                "margin_trend": "UNKNOWN",
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


def test_lookup_only_mode_lists_candidates_without_downloading(
    script_module,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "schema_version": "r11_batch_real_pdf_baseline_config_v1",
            "cases": [
                {
                    "ticker": "COMB.N0000",
                    "company_name": "Commercial Bank of Ceylon PLC",
                    "report_text_filter": "Interim Financial Statements",
                }
            ],
        },
    )
    reports = [
        _make_report(
            report_id=101,
            symbol="COMB",
            company="Commercial Bank of Ceylon PLC",
            file_text="Interim Financial Statements 31 March 2026",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/comb_q1_2026.pdf",
        )
    ]

    monkeypatch.setattr(script_module, "load_financial_reports", lambda **kwargs: reports)
    monkeypatch.setattr(
        script_module,
        "fetch_selected_report_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fetch should not run")),
    )

    exit_code = script_module.main(["--config", str(config_path), "--lookup-only"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "lookup candidates for COMB.N0000: count=1" in output
    assert "full_url: https://cdn.cse.lk/cmt/upload_report_file/comb_q1_2026.pdf" in output


def test_dry_run_does_not_write_runtime_outputs(
    script_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "schema_version": "r11_batch_real_pdf_baseline_config_v1",
            "cases": [{"ticker": "COMB.N0000"}],
        },
    )
    monkeypatch.setattr(script_module, "DEFAULT_R10_PDF_DIR", tmp_path / ".r10_runtime" / "pdfs")
    monkeypatch.setattr(
        script_module,
        "DEFAULT_R11_ANALYSIS_DIR",
        tmp_path / ".r11_runtime" / "analysis",
    )
    monkeypatch.setattr(
        script_module,
        "DEFAULT_R11_VALIDATION_DIR",
        tmp_path / ".r11_runtime" / "validation",
    )
    monkeypatch.setattr(
        script_module,
        "DEFAULT_REPORT_PATH",
        tmp_path / ".r11_runtime" / "validation" / "report.json",
    )
    reports = [
        _make_report(
            report_id=101,
            symbol="COMB",
            company="Commercial Bank of Ceylon PLC",
            file_text="Interim Financial Statements 31 March 2026",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/comb_q1_2026.pdf",
        )
    ]
    monkeypatch.setattr(script_module, "load_financial_reports", lambda **kwargs: reports)

    exit_code = script_module.main(["--config", str(config_path), "--fetch", "--dry-run"])

    assert exit_code == 0
    assert not (tmp_path / ".r10_runtime").exists()
    assert not (tmp_path / ".r11_runtime").exists()


def test_fetch_mode_refuses_ambiguous_multiple_candidate_reports(
    script_module,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "schema_version": "r11_batch_real_pdf_baseline_config_v1",
            "cases": [{"ticker": "COMB.N0000"}],
        },
    )
    reports = [
        _make_report(
            report_id=101,
            symbol="COMB",
            company="Commercial Bank of Ceylon PLC",
            file_text="Interim Financial Statements 31 March 2026 A",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/comb_a.pdf",
        ),
        _make_report(
            report_id=102,
            symbol="COMB",
            company="Commercial Bank of Ceylon PLC",
            file_text="Interim Financial Statements 31 March 2026 B",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/comb_b.pdf",
        ),
    ]
    monkeypatch.setattr(script_module, "load_financial_reports", lambda **kwargs: reports)

    exit_code = script_module.main(["--config", str(config_path), "--fetch"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "AMBIGUOUS" in output
    assert "manual selection is required" in output


def test_inspect_mode_can_use_monkeypatched_inspection_call(
    script_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "schema_version": "r11_batch_real_pdf_baseline_config_v1",
            "cases": [{"ticker": "COMB.N0000"}],
        },
    )
    monkeypatch.setattr(script_module, "DEFAULT_R10_PDF_DIR", tmp_path / ".r10_runtime" / "pdfs")
    monkeypatch.setattr(
        script_module,
        "DEFAULT_R11_ANALYSIS_DIR",
        tmp_path / ".r11_runtime" / "analysis",
    )
    monkeypatch.setattr(
        script_module,
        "DEFAULT_REPORT_PATH",
        tmp_path / ".r11_runtime" / "validation" / "report.json",
    )
    report = _make_report(
        report_id=101,
        symbol="COMB",
        company="Commercial Bank of Ceylon PLC",
        file_text="Interim Financial Statements 31 March 2026",
        manual_date_ms=1774895400000,
        path="cmt/upload_report_file/comb_q1_2026.pdf",
    )
    reports = [report]
    monkeypatch.setattr(script_module, "load_financial_reports", lambda **kwargs: reports)
    pdf_path = script_module.resolve_pdf_path_for_report(report, ticker="COMB.N0000")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_inspect_local_pdf(*, pdf_path: Path, analysis_path: Path, metric_entity: str):
        assert metric_entity == "group"
        payload = _make_analysis_payload()
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        return payload

    monkeypatch.setattr(script_module, "inspect_local_pdf", fake_inspect_local_pdf)

    exit_code = script_module.main(["--config", str(config_path), "--inspect"])

    assert exit_code == 0
    analysis_path = script_module.resolve_analysis_path_for_report(report, ticker="COMB.N0000")
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "r11_deterministic_analysis_v1"


def test_validate_mode_skips_cases_missing_expected_pages_and_builds_manifest_only_for_known_cases(
    script_module,
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "schema_version": "r11_batch_real_pdf_baseline_config_v1",
            "cases": [
                {
                    "ticker": "COMB.N0000",
                    "expected_pages": [
                        {"page_number": 2, "statement_type": "INCOME_STATEMENT"},
                        {"page_number": 4, "statement_type": "BALANCE_SHEET"},
                    ],
                    "min_verified_metrics": 1,
                    "min_aggregated_metrics": 1,
                    "expect_manual_review": False,
                },
                {
                    "ticker": "SAMP.N0000",
                    "company_name": "Sampath Bank PLC",
                    "report_text_filter": "Interim Financial Statements",
                },
            ],
        },
    )
    monkeypatch.setattr(script_module, "DEFAULT_R10_PDF_DIR", tmp_path / ".r10_runtime" / "pdfs")
    monkeypatch.setattr(
        script_module,
        "DEFAULT_R11_ANALYSIS_DIR",
        tmp_path / ".r11_runtime" / "analysis",
    )
    monkeypatch.setattr(
        script_module,
        "DEFAULT_MANIFEST_PATH",
        tmp_path / ".r11_runtime" / "validation" / "manifest.json",
    )
    monkeypatch.setattr(
        script_module,
        "DEFAULT_REPORT_PATH",
        tmp_path / ".r11_runtime" / "validation" / "report.json",
    )
    comb_report = _make_report(
        report_id=101,
        symbol="COMB",
        company="Commercial Bank of Ceylon PLC",
        file_text="Interim Financial Statements 31 March 2026",
        manual_date_ms=1774895400000,
        path="cmt/upload_report_file/comb_q1_2026.pdf",
    )
    samp_report = _make_report(
        report_id=102,
        symbol="SAMP",
        company="Sampath Bank PLC",
        file_text="Interim Financial Statements 31 March 2026",
        manual_date_ms=1774895400001,
        path="cmt/upload_report_file/samp_q1_2026.pdf",
    )
    monkeypatch.setattr(
        script_module,
        "load_financial_reports",
        lambda **kwargs: [comb_report, samp_report],
    )

    analysis_path = script_module.resolve_analysis_path_for_report(
        comb_report,
        ticker="COMB.N0000",
    )
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.write_text(
        json.dumps(_make_analysis_payload()),
        encoding="utf-8",
        newline="\n",
    )

    exit_code = script_module.main(["--config", str(config_path), "--validate"])

    assert exit_code == 1
    manifest_path = script_module.DEFAULT_MANIFEST_PATH
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest_payload["cases"]) == 1
    assert manifest_payload["cases"][0]["ticker"] == "COMB.N0000"

    report_payload = json.loads(script_module.DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))
    case_results = report_payload["case_results"]
    expectation_needed = {
        case["ticker"]: case["expectation_needed"] for case in case_results
    }
    assert expectation_needed["SAMP.N0000"] is True
    assert expectation_needed["COMB.N0000"] is False


def test_runtime_artifact_paths_resolve_under_runtime_directories(script_module) -> None:
    report = _make_report(
        report_id=101,
        symbol="COMB",
        company="Commercial Bank of Ceylon PLC",
        file_text="Interim Financial Statements 31 March 2026",
        manual_date_ms=1774895400000,
        path="cmt/upload_report_file/comb_q1_2026.pdf",
    )

    pdf_path = script_module.resolve_pdf_path_for_report(report, ticker="COMB.N0000")
    analysis_path = script_module.resolve_analysis_path_for_report(
        report,
        ticker="COMB.N0000",
    )

    assert ".r10_runtime" in str(pdf_path)
    assert ".r11_runtime" in str(analysis_path)


def test_no_test_calls_deepseek_or_network(script_module) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "DeepSeek" not in source
    assert "DEEPSEEK" not in source
    assert hasattr(script_module, "lookup_matching_reports")
