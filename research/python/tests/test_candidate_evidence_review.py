from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from candidate_evidence_review import (  # noqa: E402
    build_candidate_evidence_review,
    run_candidate_evidence_review,
)
from universe_candidate_report import UniverseCandidateFilters  # noqa: E402


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_snapshot(
    ticker: str,
    timestamp: int,
    *,
    best_bid: float | None = 9.9,
    best_ask: float | None = 10.0,
    volume: float | None = 1_000,
    turnover: float | None = 20_000,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "ticker": ticker,
        "timestamp": timestamp,
        "lastPrice": 10.0,
    }
    if best_bid is not None:
        snapshot["bestBid"] = best_bid
    if best_ask is not None:
        snapshot["bestAsk"] = best_ask
    if volume is not None:
        snapshot["volume"] = volume
    if turnover is not None:
        snapshot["totalTurnover"] = turnover
    return snapshot


def build_diagnostics_rows(scan_mode: str, unique_tickers: list[int]) -> list[dict[str, object]]:
    return [
        {
            "tickNumber": index + 1,
            "capturedAt": f"2026-06-03T04:{index:02d}:00.000Z",
            "marketState": "OPEN",
            "rawRows": coverage,
            "rawRowsExtracted": coverage,
            "acceptedSnapshots": coverage,
            "usableSnapshots": coverage,
            "quarantinedSnapshots": 0,
            "rejectedSnapshots": 0,
            "placeholderRows": 0,
            "inactiveRows": 0,
            "zeroVolumeRows": 0,
            "trainingGradeCandidate": "no",
            "fullGridScan": True,
            "scanMode": scan_mode,
            "scanSteps": 1,
            "uniqueTickers": coverage,
            "duplicateRows": 0,
            "storeScanRejectedReason": None,
            "topRejectReasons": [],
        }
        for index, coverage in enumerate(unique_tickers)
    ]


def build_session_payload(
    session_id: str,
    *,
    snapshots: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "startedAt": "2026-06-03T04:00:00.000Z",
        "endedAt": "2026-06-03T04:30:00.000Z",
        "source": "atrad-full-watch-equity",
        "mode": "read-only-local-recording",
        "snapshots": snapshots,
        "diagnostics": diagnostics,
        "totals": {
            "ticksAttempted": len(diagnostics),
            "usableSnapshots": len(snapshots),
            "quarantinedSnapshots": 0,
            "rejectedSnapshots": 0,
        },
    }


def build_variant_row(
    name: str,
    *,
    replayed_snapshots: int,
    signals_generated: int,
    signal_ticker_counts: list[tuple[str, int]] | None = None,
    unique_signal_tickers: int | None = None,
) -> dict[str, object]:
    counts = signal_ticker_counts or []
    return {
        "variantName": name,
        "diagnosticOnly": name != "baseline",
        "description": name,
        "parameterOverrides": {},
        "runtimeMode": "SHADOW",
        "replayedSnapshots": replayed_snapshots,
        "signalsGenerated": signals_generated,
        "uniqueSignalTickers": unique_signal_tickers if unique_signal_tickers is not None else len(counts),
        "generatedStrategies": [],
        "signalTickerCounts": [{"ticker": ticker, "count": count} for ticker, count in counts],
    }


def build_variant_export(
    input_path: str,
    *,
    session_id: str,
    total_snapshots: int,
    unique_tickers: int,
    variant_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "inputPath": input_path,
        "source": "atrad-full-watch-equity",
        "startedAt": "2026-06-03T04:00:00.000Z",
        "endedAt": "2026-06-03T04:30:00.000Z",
        "totalSnapshotsLoaded": total_snapshots,
        "uniqueTickers": unique_tickers,
        "topSignalTickerLimit": 10,
        "variants": variant_rows,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_root_happy_path_prints_summary_detail_and_safety_note() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1), build_snapshot("KEEP.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=1,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    ),
                    build_variant_row(
                        "imbalance-disabled-diagnostic",
                        replayed_snapshots=2,
                        signals_generated=1,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    ),
                ],
            ),
        )

        output = io.StringIO()
        run_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters(), output=output)
        text = output.getvalue()

        assert "Candidate review summary" in text
        assert "Candidate detail rows" in text
        assert "Safety note" in text
        assert "KEEP.N0000" in text
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_repeated_ticker_across_sessions_gets_tier_a_and_manual_review() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_specs = [
            ("session-a", "store_fallback_scroll", [500, 505]),
            ("session-b", "store_reconstructed", [25, 25]),
        ]
        for name, scan_mode, coverage in session_specs:
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[build_snapshot("KEEP.N0000", 1), build_snapshot("KEEP.N0000", 2)],
                    diagnostics=build_diagnostics_rows(scan_mode, coverage),
                ),
            )
            write_json(
                runtime_root / name / "variant-comparison.json",
                build_variant_export(
                    str(session_path),
                    session_id=f"{name}-id",
                    total_snapshots=2,
                    unique_tickers=1,
                    variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
                ),
            )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())
        row = report.summary_rows[0]

        assert row.ticker == "KEEP.N0000"
        assert row.tier == "Tier A"
        assert row.review_status == "MANUAL_REVIEW"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_strong_only_single_session_gets_tier_b_and_watchlist_research() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "strong.json"
        write_json(
            session_path,
            build_session_payload(
                "strong-id",
                snapshots=[build_snapshot("SOLO.N0000", 1), build_snapshot("SOLO.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "strong" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="strong-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("SOLO.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())

        assert report.summary_rows[0].tier == "Tier B"
        assert report.summary_rows[0].review_status == "WATCHLIST_RESEARCH"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_partial_only_ticker_gets_tier_c_low_confidence_and_partial_note() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "partial.json"
        write_json(
            session_path,
            build_session_payload(
                "partial-id",
                snapshots=[build_snapshot("PART.N0000", 1), build_snapshot("PART.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25, 25]),
            ),
        )
        write_json(
            runtime_root / "partial" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="partial-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("PART.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())
        row = report.summary_rows[0]

        assert row.tier == "Tier C"
        assert row.review_status == "LOW_CONFIDENCE"
        assert "partial-coverage-only" in row.notes
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_diagnostic_only_single_session_falls_back_to_tier_d() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "diag.json"
        write_json(
            session_path,
            build_session_payload(
                "diag-id",
                snapshots=[build_snapshot("DIAG.N0000", 1), build_snapshot("DIAG.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "diag" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="diag-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[build_variant_row("imbalance-disabled-diagnostic", replayed_snapshots=2, signals_generated=2, signal_ticker_counts=[("DIAG.N0000", 2)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())
        row = report.summary_rows[0]

        assert row.tier == "Tier D"
        assert row.review_status == "INSUFFICIENT_EVIDENCE"
        assert "diagnostic-only" in row.notes
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_per_variant_rollup_populates_total_baseline_diagnostic_and_variants() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "rollup.json"
        write_json(
            session_path,
            build_session_payload(
                "rollup-id",
                snapshots=[build_snapshot("ROLL.N0000", 1), build_snapshot("ROLL.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "rollup" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="rollup-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("ROLL.N0000", 1)]),
                    build_variant_row("volume-ratio-disabled-diagnostic", replayed_snapshots=2, signals_generated=2, signal_ticker_counts=[("ROLL.N0000", 2)]),
                    build_variant_row("imbalance-disabled-diagnostic", replayed_snapshots=2, signals_generated=3, signal_ticker_counts=[("ROLL.N0000", 3)]),
                    build_variant_row("volume-and-imbalance-disabled-diagnostic", replayed_snapshots=2, signals_generated=4, signal_ticker_counts=[("ROLL.N0000", 4)]),
                ],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())
        row = report.summary_rows[0]

        assert row.total_count == 10
        assert row.baseline_count == 1
        assert row.diagnostic_count == 9
        assert row.variants == ("base", "vol-off", "imb-off", "both-off")
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_best_metric_rollups_take_best_spread_best_coverage_and_max_turnover() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_specs = [
            (
                "session-a",
                "store_fallback_scroll",
                [500, 505],
                [
                    build_snapshot("BEST.N0000", 1, best_bid=9.9, best_ask=10.0, turnover=10_000),
                    build_snapshot("BEST.N0000", 2, best_bid=10.0, best_ask=10.1, turnover=11_000),
                ],
            ),
            (
                "session-b",
                "store_reconstructed",
                [25, 25],
                [
                    build_snapshot("BEST.N0000", 1, best_bid=9.9, best_ask=10.0, turnover=19_000),
                    build_snapshot("BEST.N0000", 2, best_bid=None, best_ask=None, turnover=20_000),
                ],
            ),
        ]
        for name, scan_mode, coverage, snapshots in session_specs:
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=snapshots,
                    diagnostics=build_diagnostics_rows(scan_mode, coverage),
                ),
            )
            write_json(
                runtime_root / name / "variant-comparison.json",
                build_variant_export(
                    str(session_path),
                    session_id=f"{name}-id",
                    total_snapshots=2,
                    unique_tickers=1,
                    variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("BEST.N0000", 1)])],
                ),
            )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())
        row = report.summary_rows[0]

        assert abs(row.best_median_spread_percent - 0.9950495049504915) < 1e-12
        assert row.best_bid_ask_coverage_ratio == 1.0
        assert row.max_latest_turnover == 20_000
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_unreadable_raw_session_json_prints_warning_and_skips_review_rows() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        missing_session_path = directory / "missing.json"
        write_json(
            runtime_root / "missing" / "variant-comparison.json",
            build_variant_export(
                str(missing_session_path),
                session_id="missing-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("MISS.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())

        assert report.summary_rows == []
        assert report.detail_rows == []
        assert any("session JSON unreadable" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_truncated_partial_export_marks_lower_bound_note_and_warning() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "partial.json"
        write_json(
            session_path,
            build_session_payload(
                "partial-id",
                snapshots=[build_snapshot("KEEP.N0000", 1), build_snapshot("KEEP.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25, 25]),
            ),
        )
        write_json(
            runtime_root / "partial" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="partial-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=3, unique_signal_tickers=3, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())

        assert report.detail_rows[0].notes == "lower-bound"
        assert "lower-bound" in report.summary_rows[0].notes
        assert any("lower bounds" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_deterministic_ordering_for_summary_and_detail_rows() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "sorted.json"
        write_json(
            session_path,
            build_session_payload(
                "sorted-id",
                snapshots=[
                    build_snapshot("BETA.N0000", 1),
                    build_snapshot("ALFA.N0000", 2),
                ],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "sorted" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="sorted-id",
                total_snapshots=2,
                unique_tickers=2,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=2, signal_ticker_counts=[("BETA.N0000", 1), ("ALFA.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_review(runtime_root, [], UniverseCandidateFilters())

        assert [row.ticker for row in report.summary_rows] == ["ALFA.N0000", "BETA.N0000"]
        assert [
            (row.ticker, row.session_stem, row.variant_label) for row in report.detail_rows
        ] == [
            ("ALFA.N0000", "sorted", "base"),
            ("BETA.N0000", "sorted", "base"),
        ]
    finally:
        shutil.rmtree(directory, ignore_errors=True)
