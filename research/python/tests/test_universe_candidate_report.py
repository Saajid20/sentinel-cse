from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "universe_candidate_report.py"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from universe_candidate_report import (  # noqa: E402
    build_universe_candidate_report,
    format_universe_candidate_report,
)


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_snapshot(
    ticker: str,
    timestamp: int,
    *,
    last_price: float | None = 10.0,
    best_bid: float | None = 9.9,
    best_ask: float | None = 10.1,
    volume: float | None = 1_000,
    turnover: float | None = 10_000,
    company_name: str | None = None,
    quality_status: str | None = None,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "ticker": ticker,
        "timestamp": timestamp,
    }
    if last_price is not None:
        snapshot["lastPrice"] = last_price
    if best_bid is not None:
        snapshot["bestBid"] = best_bid
    if best_ask is not None:
        snapshot["bestAsk"] = best_ask
    if volume is not None:
        snapshot["volume"] = volume
    if turnover is not None:
        snapshot["totalTurnover"] = turnover

    metadata: dict[str, object] = {}
    if company_name is not None:
        metadata["companyName"] = company_name
    if quality_status is not None:
        metadata["qualityStatus"] = quality_status
    if metadata:
        snapshot["metadata"] = metadata

    return snapshot


def build_session(snapshots: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sessionId": "unit-test-session",
        "startedAt": "2026-05-26T05:47:22.000Z",
        "endedAt": "2026-05-26T06:17:22.000Z",
        "source": "atrad-full-watch-equity",
        "mode": "read-only-local-recording",
        "snapshots": snapshots,
    }


def test_ranking_prefers_higher_snapshot_count() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1),
            build_snapshot("ALFA.N0000", 2),
            build_snapshot("BETA.N0000", 1),
        ]
    )

    report = build_universe_candidate_report(session)

    assert [candidate.ticker for candidate in report.candidates[:2]] == ["ALFA.N0000", "BETA.N0000"]


def test_ranking_prefers_better_bid_ask_coverage() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, best_bid=9.9, best_ask=10.1),
            build_snapshot("ALFA.N0000", 2, best_bid=None, best_ask=None),
            build_snapshot("BETA.N0000", 1, best_bid=9.9, best_ask=10.1),
            build_snapshot("BETA.N0000", 2, best_bid=10.0, best_ask=10.2),
        ]
    )

    report = build_universe_candidate_report(session)

    assert [candidate.ticker for candidate in report.candidates[:2]] == ["BETA.N0000", "ALFA.N0000"]


def test_ranking_prefers_lower_median_spread_when_other_metrics_tie() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, best_bid=9.0, best_ask=10.0, turnover=20_000),
            build_snapshot("ALFA.N0000", 2, best_bid=9.0, best_ask=10.0, turnover=25_000),
            build_snapshot("BETA.N0000", 1, best_bid=9.8, best_ask=10.0, turnover=20_000),
            build_snapshot("BETA.N0000", 2, best_bid=9.8, best_ask=10.0, turnover=25_000),
        ]
    )

    report = build_universe_candidate_report(session)

    assert [candidate.ticker for candidate in report.candidates[:2]] == ["BETA.N0000", "ALFA.N0000"]


def test_missing_bid_ask_volume_turnover_does_not_crash() -> None:
    session = build_session(
        [
            build_snapshot(
                "MISS.N0000",
                1,
                best_bid=None,
                best_ask=None,
                volume=None,
                turnover=None,
                last_price=None,
            )
        ]
    )

    report = build_universe_candidate_report(session)
    candidate = report.candidates[0]
    text = format_universe_candidate_report(report)

    assert candidate.bid_ask_available_count == 0
    assert candidate.average_spread_percent is None
    assert candidate.latest_volume is None
    assert candidate.latest_turnover is None
    assert "unavailable" in text


def test_quality_status_breakdown_is_summarized_when_present() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, company_name="Alfa PLC", quality_status="HIGH_CONFIDENCE"),
            build_snapshot("ALFA.N0000", 2, company_name="Alfa PLC", quality_status="HIGH_CONFIDENCE"),
            build_snapshot("ALFA.N0000", 3, company_name="Alfa PLC", quality_status="MEDIUM_CONFIDENCE"),
        ]
    )

    report = build_universe_candidate_report(session)
    candidate = report.candidates[0]
    text = format_universe_candidate_report(report)

    assert candidate.company_name == "Alfa PLC"
    assert candidate.quality_status_counts == {
        "HIGH_CONFIDENCE": 2,
        "MEDIUM_CONFIDENCE": 1,
    }
    assert "HIGH_CONFIDENCE:2, MEDIUM_CONFIDENCE:1" in text


def test_top_argument_limits_report_rows() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1),
            build_snapshot("ALFA.N0000", 2),
            build_snapshot("BETA.N0000", 1),
            build_snapshot("BETA.N0000", 2),
            build_snapshot("CALT.N0000", 1),
        ]
    )

    report = build_universe_candidate_report(session, top=2)

    assert [candidate.ticker for candidate in report.candidates] == ["ALFA.N0000", "BETA.N0000"]


def test_cli_top_behavior_displays_only_requested_rows() -> None:
    directory = make_temp_dir()
    try:
        session_path = directory / "session.json"
        session_path.write_text(
            json.dumps(
                build_session(
                    [
                        build_snapshot("ALFA.N0000", 1),
                        build_snapshot("ALFA.N0000", 2),
                        build_snapshot("BETA.N0000", 1),
                        build_snapshot("BETA.N0000", 2),
                        build_snapshot("CALT.N0000", 1),
                    ]
                )
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--input", str(session_path), "--top", "2"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0
        assert "ALFA.N0000" in completed.stdout
        assert "BETA.N0000" in completed.stdout
        assert "CALT.N0000" not in completed.stdout
    finally:
        shutil.rmtree(directory, ignore_errors=True)
