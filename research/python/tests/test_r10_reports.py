from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.reports import (  # noqa: E402
    LocalReportStore,
    R10AnalysisReport,
    ReportType,
    build_report_id,
)


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-reports-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def make_analysis_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "schema_version": "r10_news_analyst_v1",
        "analysis_scope": "MARKET",
        "ticker": None,
        "sector": None,
        "macro_risk_level": "MEDIUM",
        "sentiment": "NEUTRAL",
        "catalyst_tags": ["MACRO"],
        "affected_tickers": [],
        "affected_sectors": ["DIVERSIFIED"],
        "signal_policy": "MANUAL_REVIEW",
        "manual_review_required": True,
        "confidence": 0.64,
        "valid_until": "2026-05-24T00:00:00Z",
        "staleness_risk": "MEDIUM",
        "reason_codes": ["INFO_ONLY"],
        "short_summary": "The validated context should be retained for offline review.",
        "sources": [
            {
                "source_type": "CSE_DISCLOSURE",
                "title": "Corporate disclosure PDF",
                "url": "https://cdn.cse.lk/cmt/announcement_portal_prod/disclosure.pdf",
                "published_at": "2026-05-23T10:00:00Z",
                "retrieved_at": "2026-05-23T10:30:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def make_report(**overrides: object) -> R10AnalysisReport:
    payload = {
        "report_id": "r10_market_context_20260524T120000Z_COMB.N0000",
        "report_type": "MARKET_CONTEXT",
        "generated_at": "2026-05-24T12:00:00Z",
        "query": {"keywords": ["COMB.N0000", "market context"], "limit": 1},
        "analysis": make_analysis_payload(),
        "source_document_ids": [" doc-001 ", "", " doc-002 "],
        "notes": "  offline verification only  ",
    }
    payload.update(overrides)
    return R10AnalysisReport.model_validate(payload)


def test_r10_analysis_report_accepts_valid_data() -> None:
    report = make_report()

    assert report.schema_version == "r10_analysis_report_v1"
    assert report.report_type is ReportType.MARKET_CONTEXT
    assert report.analysis.schema_version == "r10_news_analyst_v1"


def test_schema_version_is_locked() -> None:
    with pytest.raises(ValidationError, match="r10_analysis_report_v1"):
        make_report(schema_version="r10_analysis_report_v2")


def test_empty_report_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="report_id must not be empty"):
        make_report(report_id="   ")


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValidationError, match="query must not be empty"):
        make_report(query={})


def test_source_document_ids_are_stripped_and_empty_entries_removed() -> None:
    report = make_report(source_document_ids=[" doc-001 ", " ", "", "doc-002"])

    assert report.source_document_ids == ["doc-001", "doc-002"]


def test_notes_empty_string_becomes_none() -> None:
    report = make_report(notes="   ")

    assert report.notes is None


def test_build_report_id_creates_safe_deterministic_filename_friendly_value() -> None:
    generated_at = datetime(2026, 5, 24, 12, 34, 56, tzinfo=UTC)

    report_id = build_report_id(
        ReportType.TICKER_CONTEXT,
        generated_at,
        scope_key="JKH.N0000 / Corporate Disclosure",
    )

    assert report_id == (
        "r10_ticker_context_20260524T123456Z_JKH.N0000_Corporate_Disclosure"
    )


def test_local_report_store_save_writes_json_file(tmp_path: Path) -> None:
    store = LocalReportStore(tmp_path / "reports")
    report = make_report()

    path = store.save(report)

    assert path.exists()
    assert path.name == f"{report.report_id}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["report_id"] == report.report_id


def test_local_report_store_load_validates_saved_report(tmp_path: Path) -> None:
    store = LocalReportStore(tmp_path / "reports")
    report = make_report()
    path = store.save(report)

    loaded = store.load(path)

    assert loaded == report


def test_local_report_store_list_reports_returns_sorted_json_files(tmp_path: Path) -> None:
    store = LocalReportStore(tmp_path / "reports")
    second = make_report(
        report_id="r10_market_context_20260524T120100Z_beta",
        generated_at="2026-05-24T12:01:00Z",
    )
    first = make_report(
        report_id="r10_market_context_20260524T120000Z_alpha",
        generated_at="2026-05-24T12:00:00Z",
    )
    store.save(second)
    store.save(first)

    paths = store.list_reports()

    assert [path.name for path in paths] == [
        "r10_market_context_20260524T120000Z_alpha.json",
        "r10_market_context_20260524T120100Z_beta.json",
    ]


def test_local_report_store_clear_deletes_only_json_files(tmp_path: Path) -> None:
    store_directory = tmp_path / "reports"
    store = LocalReportStore(store_directory)
    store.save(make_report())
    (store_directory / "notes.txt").write_text("keep", encoding="utf-8")
    subdirectory = store_directory / "archive"
    subdirectory.mkdir()
    (subdirectory / "old.json").write_text("{}", encoding="utf-8")

    store.clear()

    assert store.list_reports() == []
    assert (store_directory / "notes.txt").exists()
    assert (subdirectory / "old.json").exists()
