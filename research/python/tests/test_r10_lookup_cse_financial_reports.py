from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.ingestion import CseFinancialReport  # noqa: E402

SCRIPT_PATH = PYTHON_ROOT / "scripts" / "r10_lookup_cse_financial_reports.py"


@pytest.fixture
def script_module():
    spec = importlib.util.spec_from_file_location(
        "r10_lookup_cse_financial_reports",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
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


def test_filter_financial_reports_matches_bare_and_full_ticker(script_module) -> None:
    reports = [
        _make_report(
            report_id=1,
            symbol="DIAL",
            company="Dialog Axiata PLC",
            file_text="Interim Financial Statements",
            manual_date_ms=1767225600000,
            path="cmt/upload_report_file/dial.pdf",
        ),
        _make_report(
            report_id=2,
            symbol="JKH",
            company="John Keells Holdings PLC",
            file_text="Interim Financial Statements",
            manual_date_ms=1767225600000,
            path="cmt/upload_report_file/jkh.pdf",
        ),
    ]

    dial_bare = script_module.filter_financial_reports(reports, ticker="DIAL")
    dial_full = script_module.filter_financial_reports(reports, ticker="DIAL.N0000")

    assert [report.symbol for report in dial_bare] == ["DIAL"]
    assert [report.symbol for report in dial_full] == ["DIAL"]


def test_filter_financial_reports_text_filter_works(script_module) -> None:
    reports = [
        _make_report(
            report_id=1,
            symbol="DIAL",
            company="Dialog Axiata PLC",
            file_text="Interim Financial Statements",
            manual_date_ms=1767225600000,
            path="cmt/upload_report_file/dial.pdf",
        ),
        _make_report(
            report_id=2,
            symbol="JKH",
            company="John Keells Holdings PLC",
            file_text="Annual Report",
            manual_date_ms=1767225600000,
            path="cmt/upload_report_file/jkh.pdf",
        ),
    ]

    filtered = script_module.filter_financial_reports(
        reports,
        text_filter="interim financial statements",
    )

    assert [report.symbol for report in filtered] == ["DIAL"]


def test_filter_financial_reports_date_filter_uses_manual_date(script_module) -> None:
    reports = [
        _make_report(
            report_id=1,
            symbol="DIAL",
            company="Dialog Axiata PLC",
            file_text="Interim Financial Statements",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/dial.pdf",
        ),
        _make_report(
            report_id=2,
            symbol="JKH",
            company="John Keells Holdings PLC",
            file_text="Interim Financial Statements",
            manual_date_ms=1761782400000,
            path="cmt/upload_report_file/jkh.pdf",
        ),
    ]

    filtered = script_module.filter_financial_reports(
        reports,
        from_date=script_module.date(2026, 3, 1),
        to_date=script_module.date(2026, 4, 30),
    )

    assert [report.symbol for report in filtered] == ["DIAL"]


def test_main_prints_candidate_report_info_and_pdf_url(
    script_module,
    monkeypatch,
    capsys,
) -> None:
    reports = [
        _make_report(
            report_id=1,
            symbol="DIAL",
            company="Dialog Axiata PLC",
            file_text="Interim Financial Statements for the Quarter ended 31st March 2026",
            manual_date_ms=1774895400000,
            path="cmt/upload_report_file/dial.pdf",
        )
    ]

    monkeypatch.setattr(
        script_module.CseApiClient,
        "get_financial_reports",
        lambda self: reports,
    )

    exit_code = script_module.main(
        [
            "--ticker",
            "DIAL.N0000",
            "--from-date",
            "2026-01-01",
            "--to-date",
            "2026-12-31",
            "--top",
            "10",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "CSE Financial Reports Lookup" in output
    assert "count: 1" in output
    assert "symbol: DIAL" in output
    assert "company: Dialog Axiata PLC" in output
    assert "file_text: Interim Financial Statements for the Quarter ended 31st March 2026" in output
    assert "path: cmt/upload_report_file/dial.pdf" in output
    assert "full_url: https://cdn.cse.lk/cmt/upload_report_file/dial.pdf" in output


def test_no_test_calls_deepseek_or_network(script_module) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "DeepSeek" not in source
    assert "DEEPSEEK" not in source
    assert hasattr(script_module, "filter_financial_reports")
