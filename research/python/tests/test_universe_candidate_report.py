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
    UniverseCandidateFilters,
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


def test_min_snapshots_filters_low_observation_tickers() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1),
            build_snapshot("ALFA.N0000", 2),
            build_snapshot("BETA.N0000", 1),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_snapshots=2),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["ALFA.N0000"]
    assert report.original_candidate_count == 2
    assert report.filtered_candidate_count == 1


def test_min_bid_ask_coverage_filters_partial_candidates() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1),
            build_snapshot("ALFA.N0000", 2, best_bid=None, best_ask=None),
            build_snapshot("BETA.N0000", 1),
            build_snapshot("BETA.N0000", 2),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_bid_ask_coverage=0.8),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["BETA.N0000"]


def test_max_median_spread_filters_wide_spread_tickers() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, best_bid=9.9, best_ask=10.0),
            build_snapshot("ALFA.N0000", 2, best_bid=9.9, best_ask=10.0),
            build_snapshot("BETA.N0000", 1, best_bid=8.0, best_ask=10.0),
            build_snapshot("BETA.N0000", 2, best_bid=8.0, best_ask=10.0),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(max_median_spread=1.5),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["ALFA.N0000"]


def test_min_latest_turnover_filters_low_turnover_tickers() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, turnover=25_000),
            build_snapshot("BETA.N0000", 1, turnover=5_000),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_latest_turnover=10_000),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["ALFA.N0000"]


def test_min_max_volume_filters_low_volume_tickers() -> None:
    session = build_session(
        [
            build_snapshot("ALFA.N0000", 1, volume=20_000),
            build_snapshot("ALFA.N0000", 2, volume=25_000),
            build_snapshot("BETA.N0000", 1, volume=5_000),
            build_snapshot("BETA.N0000", 2, volume=7_000),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_max_volume=10_000),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["ALFA.N0000"]


def test_exclude_non_voting_removes_x0000() -> None:
    session = build_session(
        [
            build_snapshot("SEYB.X0000", 1),
            build_snapshot("SEYB.X0000", 2),
            build_snapshot("COMB.N0000", 1),
            build_snapshot("COMB.N0000", 2),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(exclude_non_voting=True),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["COMB.N0000"]


def test_repeatable_exclude_pattern_removes_matching_suffixes() -> None:
    session = build_session(
        [
            build_snapshot("SEYB.X0000", 1),
            build_snapshot("WARR.U0000", 1),
            build_snapshot("COMB.N0000", 1),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(exclude_patterns=[".x0000", ".U0000"]),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["COMB.N0000"]


def test_combined_filters_remain_deterministic() -> None:
    session = build_session(
        [
            build_snapshot("BETA.N0000", 1, best_bid=9.9, best_ask=10.0, volume=20_000, turnover=25_000),
            build_snapshot("BETA.N0000", 2, best_bid=9.9, best_ask=10.0, volume=21_000, turnover=26_000),
            build_snapshot("ALFA.N0000", 1, best_bid=9.7, best_ask=10.0, volume=20_000, turnover=25_000),
            build_snapshot("ALFA.N0000", 2, best_bid=9.7, best_ask=10.0, volume=21_000, turnover=26_000),
            build_snapshot("NOPE.X0000", 1, best_bid=9.9, best_ask=10.0, volume=50_000, turnover=50_000),
            build_snapshot("NOPE.X0000", 2, best_bid=9.9, best_ask=10.0, volume=50_000, turnover=50_000),
        ]
    )

    report = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(
            exclude_non_voting=True,
            min_snapshots=2,
            min_bid_ask_coverage=1.0,
            max_median_spread=3.0,
            min_latest_turnover=20_000,
            min_max_volume=20_000,
        ),
    )

    assert [candidate.ticker for candidate in report.candidates] == ["BETA.N0000", "ALFA.N0000"]


def test_missing_metrics_are_excluded_only_when_required_by_active_filter() -> None:
    session = build_session(
        [
            build_snapshot("MISS.N0000", 1, best_bid=None, best_ask=None, volume=None, turnover=None),
            build_snapshot("KEEP.N0000", 1, best_bid=9.9, best_ask=10.0, volume=20_000, turnover=30_000),
        ]
    )

    unfiltered = build_universe_candidate_report(session)
    turnover_filtered = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_latest_turnover=10_000),
    )
    volume_filtered = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(min_max_volume=10_000),
    )
    spread_filtered = build_universe_candidate_report(
        session,
        filters=UniverseCandidateFilters(max_median_spread=1.5),
    )

    assert [candidate.ticker for candidate in unfiltered.candidates] == ["KEEP.N0000", "MISS.N0000"]
    assert [candidate.ticker for candidate in turnover_filtered.candidates] == ["KEEP.N0000"]
    assert [candidate.ticker for candidate in volume_filtered.candidates] == ["KEEP.N0000"]
    assert [candidate.ticker for candidate in spread_filtered.candidates] == ["KEEP.N0000"]


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
        assert "original candidates: 3" in completed.stdout
        assert "filtered candidates: 3" in completed.stdout
        assert "top limit: 2" in completed.stdout
        assert "displayed candidates: 2" in completed.stdout
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cli_filters_apply_before_top_and_report_counts() -> None:
    directory = make_temp_dir()
    try:
        session_path = directory / "session.json"
        session_path.write_text(
            json.dumps(
                build_session(
                    [
                        build_snapshot("SEYB.X0000", 1, volume=30_000, turnover=50_000),
                        build_snapshot("SEYB.X0000", 2, volume=30_000, turnover=50_000),
                        build_snapshot("ALFA.N0000", 1, volume=30_000, turnover=50_000),
                        build_snapshot("ALFA.N0000", 2, volume=30_000, turnover=50_000),
                        build_snapshot("BETA.N0000", 1, volume=5_000, turnover=8_000),
                        build_snapshot("BETA.N0000", 2, volume=5_000, turnover=8_000),
                        build_snapshot("GAMM.U0000", 1, volume=30_000, turnover=50_000),
                        build_snapshot("GAMM.U0000", 2, volume=30_000, turnover=50_000),
                    ]
                )
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input",
                str(session_path),
                "--top",
                "5",
                "--exclude-non-voting",
                "--exclude-pattern",
                ".u0000",
                "--min-snapshots",
                "2",
                "--min-bid-ask-coverage",
                "1.0",
                "--max-median-spread",
                "2",
                "--min-latest-turnover",
                "10000",
                "--min-max-volume",
                "10000",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0
        assert "original candidates: 4" in completed.stdout
        assert "filtered candidates: 1" in completed.stdout
        assert "top limit: 5" in completed.stdout
        assert "displayed candidates: 1" in completed.stdout
        assert "ALFA.N0000" in completed.stdout
        assert "SEYB.X0000" not in completed.stdout
        assert "GAMM.U0000" not in completed.stdout
        assert "BETA.N0000" not in completed.stdout
    finally:
        shutil.rmtree(directory, ignore_errors=True)
