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

from multi_session_aggregate_report import (  # noqa: E402
    build_aggregate_rows,
    classify_coverage_type,
    format_rows_table,
    run_multi_session_aggregate_report,
)
from summarize_session import summarize_session  # noqa: E402
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
    last_price: float = 10.0,
    best_bid: float | None = 9.9,
    best_ask: float | None = 10.0,
    volume: float | None = 1_000,
    turnover: float | None = 20_000,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "ticker": ticker,
        "timestamp": timestamp,
        "lastPrice": last_price,
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


def build_diagnostics_rows(
    *,
    scan_mode: str,
    unique_tickers: list[int],
    market_state: str = "OPEN",
) -> list[dict[str, object]]:
    return [
        {
            "tickNumber": index + 1,
            "capturedAt": f"2026-06-02T04:{index:02d}:00.000Z",
            "marketState": market_state,
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
    ticks_attempted: int,
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "startedAt": "2026-06-02T04:00:00.000Z",
        "endedAt": "2026-06-02T04:30:00.000Z",
        "source": "atrad-full-watch-equity",
        "mode": "read-only-local-recording",
        "snapshots": snapshots,
        "diagnostics": diagnostics,
        "totals": {
            "ticksAttempted": ticks_attempted,
            "usableSnapshots": len(snapshots),
            "quarantinedSnapshots": 0,
            "rejectedSnapshots": 0,
        },
    }


def build_replay_export(
    input_path: str,
    *,
    session_id: str,
    unique_tickers: int,
    total_snapshots: int,
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "inputPath": input_path,
        "source": "atrad-full-watch-equity",
        "totalSnapshotsLoaded": total_snapshots,
        "replayedSnapshots": total_snapshots,
        "uniqueTickers": unique_tickers,
        "signalsGenerated": 0,
        "aggregateReplayDiagnostics": {
            "snapshotsProcessed": total_snapshots,
            "enrichedSnapshots": total_snapshots,
            "spreadBlockedCount": 1,
            "volumeBlockedCount": 2,
            "imbalanceBlockedCount": 3,
            "vwapMissingCount": 4,
            "firstFiveMinuteHighMissingCount": 5,
            "priceNotAboveVwapCount": 6,
            "priceNotAboveMomentumTriggerCount": 7,
            "insufficientHistoryCount": 8,
            "strategyReadySnapshotCount": 9,
            "likelyBlockers": ["insufficient time-series history"],
        },
        "thresholdSummary": {
            "maxSpreadPercent": 1.5,
            "minimumVolumeRatio": 2,
            "minimumImbalance": 0,
            "momentumTriggerBasis": "first5MinHighEstimate",
        },
        "perTickerConditionDiagnostics": [
            {
                "ticker": "ALFA.N0000",
                "snapshots": total_snapshots,
                "historyPass": max(total_snapshots - 1, 0),
                "strategyReady": 0,
                "spreadPass": total_snapshots,
                "vwapAvailable": total_snapshots,
                "priceAboveVwap": total_snapshots,
                "firstHighAvailable": max(total_snapshots - 1, 0),
                "momentumPass": 0,
                "volumeRatioAvailable": max(total_snapshots - 1, 0),
                "volumeRatioPass": 0,
                "imbalanceAvailable": total_snapshots,
                "imbalancePass": total_snapshots,
                "signals": 0,
                "topBlockers": ["momentum trigger blocked"],
            }
        ],
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
        "signalTickerCounts": [
            {"ticker": ticker, "count": count} for ticker, count in counts
        ],
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
        "startedAt": "2026-06-02T04:00:00.000Z",
        "endedAt": "2026-06-02T04:30:00.000Z",
        "totalSnapshotsLoaded": total_snapshots,
        "uniqueTickers": unique_tickers,
        "topSignalTickerLimit": 10,
        "variants": variant_rows,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_root_happy_path_reads_exports_and_raw_session() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "data" / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("ALFA.N0000", 1),
                    build_snapshot("ALFA.N0000", 2),
                    build_snapshot("BETA.N0000", 1),
                    build_snapshot("BETA.N0000", 2),
                    build_snapshot("GAMM.N0000", 1),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[500, 505, 510, 515, 520],
                ),
                ticks_attempted=5,
            ),
        )
        write_json(
            runtime_root / "session-a" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-a-id",
                unique_tickers=3,
                total_snapshots=5,
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=5,
                unique_tickers=3,
                variant_rows=[
                    build_variant_row("baseline", replayed_snapshots=5, signals_generated=1),
                    build_variant_row("volume-ratio-disabled-diagnostic", replayed_snapshots=5, signals_generated=2),
                    build_variant_row("imbalance-disabled-diagnostic", replayed_snapshots=5, signals_generated=3),
                    build_variant_row("volume-and-imbalance-disabled-diagnostic", replayed_snapshots=5, signals_generated=4),
                ],
            ),
        )

        rows = build_aggregate_rows(runtime_root, [])

        assert len(rows) == 1
        row = rows[0]
        assert row.session_stem == "session-a"
        assert row.session_id == "session-a-id"
        assert row.coverage_type == "strong-full-grid"
        assert row.scan_mode_summary == "store_fallback_scroll:5"
        assert row.coverage_summary == "520/510"
        assert row.baseline_signals == 1
        assert row.volume_ratio_disabled_signals == 2
        assert row.imbalance_disabled_signals == 3
        assert row.volume_and_imbalance_disabled_signals == 4
        assert row.top_blocker == "insufficient time-series history"
        assert row.notes == "-"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_input_mode_without_runtime_exports_still_prints_session_row() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-b.json"
        write_json(
            session_path,
            build_session_payload(
                "session-b-id",
                snapshots=[
                    build_snapshot("BETA.N0000", 1),
                    build_snapshot("BETA.N0000", 2),
                    build_snapshot("GAMM.N0000", 1),
                    build_snapshot("GAMM.N0000", 2),
                    build_snapshot("DELT.N0000", 1),
                ],
                diagnostics=(
                    build_diagnostics_rows(scan_mode="store_reconstructed", unique_tickers=[25, 25, 26])
                    + build_diagnostics_rows(scan_mode="store_fallback_scroll", unique_tickers=[24, 25])
                ),
                ticks_attempted=5,
            ),
        )

        rows = build_aggregate_rows(runtime_root, [session_path])

        assert len(rows) == 1
        row = rows[0]
        assert row.session_stem == "session-b"
        assert row.coverage_type == "partial-coverage"
        assert row.scan_mode_summary == "store_reconstructed:3, store_fallback_scroll:2"
        assert row.baseline_signals is None
        assert row.top_blocker == "n/a"
        assert row.notes == "missing replay export; missing variant export"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_runtime_root_with_unreadable_session_json_still_uses_runtime_fields() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        missing_session_path = directory / "missing-session.json"
        write_json(
            runtime_root / "session-c" / "replay-diagnostics.json",
            build_replay_export(
                str(missing_session_path),
                session_id="session-c-id",
                unique_tickers=96,
                total_snapshots=595,
            ),
        )
        write_json(
            runtime_root / "session-c" / "variant-comparison.json",
            build_variant_export(
                str(missing_session_path),
                session_id="session-c-id",
                total_snapshots=595,
                unique_tickers=96,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=595,
                        signals_generated=4,
                        signal_ticker_counts=[("ALFA.N0000", 4)],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(runtime_root, [])

        assert len(rows) == 1
        row = rows[0]
        assert row.session_id == "session-c-id"
        assert row.coverage_type == "unknown"
        assert row.quality_classification == "unknown"
        assert row.scan_mode_summary == "n/a"
        assert row.coverage_summary == "n/a"
        assert row.total_snapshots == 595
        assert row.unique_tickers == 96
        assert row.baseline_signals == 4
        assert row.notes == "session JSON unreadable"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_coverage_heuristic_classifies_strong_partial_and_unknown() -> None:
    strong_summary = {
        "sessionId": "strong-session",
        "startedAt": "2026-06-02T00:00:00.000Z",
        "endedAt": "2026-06-02T00:01:00.000Z",
        "source": "unit-test",
        "mode": "read-only-local-recording",
        "snapshots": [],
        "diagnostics": build_diagnostics_rows(
            scan_mode="store_fallback_scroll",
            unique_tickers=[500, 502, 504, 506, 508],
        ),
        "totals": {"ticksAttempted": 5},
    }
    partial_summary = {
        "sessionId": "partial-session",
        "startedAt": "2026-06-02T00:00:00.000Z",
        "endedAt": "2026-06-02T00:01:00.000Z",
        "source": "unit-test",
        "mode": "read-only-local-recording",
        "snapshots": [],
        "diagnostics": build_diagnostics_rows(
            scan_mode="store_reconstructed",
            unique_tickers=[25, 25, 25, 26, 24],
        ),
        "totals": {"ticksAttempted": 5},
    }

    assert classify_coverage_type(summarize_session(strong_summary)) == "strong-full-grid"
    assert classify_coverage_type(summarize_session(partial_summary)) == "partial-coverage"
    assert classify_coverage_type(None) == "unknown"


def test_runtime_root_happy_path_with_active_filters_renders_raw_and_filtered_counts() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-filtered.json"
        write_json(
            session_path,
            build_session_payload(
                "session-filtered-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, best_bid=9.9, best_ask=10.0, volume=12_000, turnover=25_000),
                    build_snapshot("KEEP.N0000", 2, best_bid=10.0, best_ask=10.1, volume=13_000, turnover=26_000),
                    build_snapshot("DROP.X0000", 1, best_bid=19.9, best_ask=20.0, volume=12_000, turnover=25_000),
                    build_snapshot("DROP.X0000", 2, best_bid=20.0, best_ask=20.1, volume=13_000, turnover=26_000),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[500, 505],
                ),
                ticks_attempted=2,
            ),
        )
        write_json(
            runtime_root / "session-filtered" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-filtered-id",
                unique_tickers=2,
                total_snapshots=4,
            ),
        )
        write_json(
            runtime_root / "session-filtered" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-filtered-id",
                total_snapshots=4,
                unique_tickers=2,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=4,
                        signals_generated=2,
                        signal_ticker_counts=[("KEEP.N0000", 1), ("DROP.X0000", 1)],
                    ),
                    build_variant_row(
                        "volume-ratio-disabled-diagnostic",
                        replayed_snapshots=4,
                        signals_generated=2,
                        signal_ticker_counts=[("KEEP.N0000", 1), ("DROP.X0000", 1)],
                    ),
                    build_variant_row(
                        "imbalance-disabled-diagnostic",
                        replayed_snapshots=4,
                        signals_generated=2,
                        signal_ticker_counts=[("KEEP.N0000", 1), ("DROP.X0000", 1)],
                    ),
                    build_variant_row(
                        "volume-and-imbalance-disabled-diagnostic",
                        replayed_snapshots=4,
                        signals_generated=2,
                        signal_ticker_counts=[("KEEP.N0000", 1), ("DROP.X0000", 1)],
                    ),
                ],
            ),
        )

        filters = UniverseCandidateFilters(exclude_non_voting=True)
        rows = build_aggregate_rows(runtime_root, [], filters=filters)
        table = format_rows_table(rows, show_filtered_columns=True)

        row = rows[0]
        assert row.coverage_type == "strong-full-grid"
        assert row.coverage_summary == "505/502.5"
        assert row.baseline_signals == 2
        assert row.volume_ratio_disabled_signals == 2
        assert row.imbalance_disabled_signals == 2
        assert row.volume_and_imbalance_disabled_signals == 2
        assert row.filtered_baseline_signals == 1
        assert row.filtered_volume_ratio_disabled_signals == 1
        assert row.filtered_imbalance_disabled_signals == 1
        assert row.filtered_volume_and_imbalance_disabled_signals == 1
        assert "f-base" in table
        assert "f-vol" in table
        assert "f-imb" in table
        assert "f-both" in table
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_exclude_pattern_support_filters_matching_signal_tickers() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-pattern.json"
        write_json(
            session_path,
            build_session_payload(
                "session-pattern-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1),
                    build_snapshot("DROP.U0000", 1),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_reconstructed",
                    unique_tickers=[25],
                ),
                ticks_attempted=1,
            ),
        )
        write_json(
            runtime_root / "session-pattern" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-pattern-id",
                total_snapshots=2,
                unique_tickers=2,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=2,
                        signal_ticker_counts=[("KEEP.N0000", 1), ("DROP.U0000", 1)],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(exclude_patterns=[".u0000"]),
        )

        assert rows[0].baseline_signals == 2
        assert rows[0].filtered_baseline_signals == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_metric_filters_exclude_signal_tickers_that_fail_thresholds() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-metrics.json"
        write_json(
            session_path,
            build_session_payload(
                "session-metrics-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, best_bid=9.9, best_ask=10.0, volume=12_000, turnover=25_000),
                    build_snapshot("KEEP.N0000", 2, best_bid=10.0, best_ask=10.1, volume=15_000, turnover=26_000),
                    build_snapshot("SNAP.N0000", 1, best_bid=9.9, best_ask=10.0, volume=12_000, turnover=25_000),
                    build_snapshot("COVR.N0000", 1, best_bid=9.9, best_ask=10.0, volume=12_000, turnover=25_000),
                    build_snapshot("COVR.N0000", 2, best_bid=None, best_ask=None, volume=15_000, turnover=26_000),
                    build_snapshot("SPRD.N0000", 1, best_bid=8.0, best_ask=10.0, volume=12_000, turnover=25_000),
                    build_snapshot("SPRD.N0000", 2, best_bid=8.0, best_ask=10.0, volume=15_000, turnover=26_000),
                    build_snapshot("TURN.N0000", 1, best_bid=9.9, best_ask=10.0, volume=12_000, turnover=5_000),
                    build_snapshot("TURN.N0000", 2, best_bid=10.0, best_ask=10.1, volume=15_000, turnover=6_000),
                    build_snapshot("VOLM.N0000", 1, best_bid=9.9, best_ask=10.0, volume=5_000, turnover=25_000),
                    build_snapshot("VOLM.N0000", 2, best_bid=10.0, best_ask=10.1, volume=6_000, turnover=26_000),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_reconstructed",
                    unique_tickers=[25, 25],
                ),
                ticks_attempted=2,
            ),
        )
        write_json(
            runtime_root / "session-metrics" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-metrics-id",
                total_snapshots=11,
                unique_tickers=6,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=11,
                        signals_generated=6,
                        signal_ticker_counts=[
                            ("KEEP.N0000", 1),
                            ("SNAP.N0000", 1),
                            ("COVR.N0000", 1),
                            ("SPRD.N0000", 1),
                            ("TURN.N0000", 1),
                            ("VOLM.N0000", 1),
                        ],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(
                min_snapshots=2,
                min_bid_ask_coverage=0.8,
                max_median_spread=1.5,
                min_latest_turnover=10_000,
                min_max_volume=10_000,
            ),
        )

        assert rows[0].baseline_signals == 6
        assert rows[0].filtered_baseline_signals == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_raw_session_json_with_filters_active_marks_filtered_counts_unavailable() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        missing_session_path = directory / "missing-filtered.json"
        write_json(
            runtime_root / "session-missing-filtered" / "variant-comparison.json",
            build_variant_export(
                str(missing_session_path),
                session_id="session-missing-filtered-id",
                total_snapshots=5,
                unique_tickers=2,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=5,
                        signals_generated=2,
                        signal_ticker_counts=[("ALFA.N0000", 1), ("BETA.X0000", 1)],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(exclude_non_voting=True),
        )

        assert rows[0].baseline_signals == 2
        assert rows[0].filtered_baseline_signals is None
        assert "session JSON unreadable" in rows[0].notes
        assert "filtered counts unavailable" in rows[0].notes
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_expected_variants_render_na_without_crashing() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-d.json"
        write_json(
            session_path,
            build_session_payload(
                "session-d-id",
                snapshots=[
                    build_snapshot("DELTA.N0000", 1),
                    build_snapshot("DELTA.N0000", 2),
                    build_snapshot("OMEGA.N0000", 1),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[450, 455, 460],
                ),
                ticks_attempted=3,
            ),
        )
        write_json(
            runtime_root / "session-d" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-d-id",
                unique_tickers=2,
                total_snapshots=3,
            ),
        )
        write_json(
            runtime_root / "session-d" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-d-id",
                total_snapshots=3,
                unique_tickers=2,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=3,
                        signals_generated=2,
                        signal_ticker_counts=[("DELTA.N0000", 2)],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(exclude_non_voting=True),
        )
        table = format_rows_table(rows, show_filtered_columns=True)

        assert rows[0].baseline_signals == 2
        assert rows[0].filtered_baseline_signals == 2
        assert rows[0].volume_ratio_disabled_signals is None
        assert rows[0].filtered_volume_ratio_disabled_signals is None
        assert "n/a" in table
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_partial_signal_ticker_counts_are_noted_when_export_is_truncated() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-partial.json"
        write_json(
            session_path,
            build_session_payload(
                "session-partial-id",
                snapshots=[
                    build_snapshot("ALFA.N0000", 1),
                    build_snapshot("ALFA.N0000", 2),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_reconstructed",
                    unique_tickers=[25, 25],
                ),
                ticks_attempted=2,
            ),
        )
        write_json(
            runtime_root / "session-partial" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-partial-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=3,
                        unique_signal_tickers=3,
                        signal_ticker_counts=[("ALFA.N0000", 1)],
                    )
                ],
            ),
        )

        rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(min_snapshots=1),
        )

        assert rows[0].filtered_baseline_signals == 1
        assert "filtered counts may be partial" in rows[0].notes
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_session_rows_are_sorted_deterministically_with_and_without_filters() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        for name in ("session-z", "session-a", "session-m"):
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[
                        build_snapshot("ALFA.N0000", 1),
                        build_snapshot("ALFA.N0000", 2),
                    ],
                    diagnostics=build_diagnostics_rows(
                        scan_mode="store_fallback_scroll",
                        unique_tickers=[400, 401],
                    ),
                    ticks_attempted=2,
                ),
            )
            write_json(
                runtime_root / name / "replay-diagnostics.json",
                build_replay_export(
                    str(session_path),
                    session_id=f"{name}-id",
                    unique_tickers=1,
                    total_snapshots=2,
                ),
            )

        rows = build_aggregate_rows(runtime_root, [])
        filtered_rows = build_aggregate_rows(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(exclude_non_voting=True),
        )

        assert [row.session_stem for row in rows] == ["session-a", "session-m", "session-z"]
        assert [row.session_stem for row in filtered_rows] == ["session-a", "session-m", "session-z"]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_run_function_prints_terminal_table() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-e.json"
        write_json(
            session_path,
            build_session_payload(
                "session-e-id",
                snapshots=[
                    build_snapshot("EPSI.N0000", 1),
                    build_snapshot("EPSI.N0000", 2),
                ],
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[500, 505],
                ),
                ticks_attempted=2,
            ),
        )
        write_json(
            runtime_root / "session-e" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-e-id",
                unique_tickers=1,
                total_snapshots=2,
            ),
        )

        output = io.StringIO()
        exit_code = run_multi_session_aggregate_report(
            runtime_root,
            [],
            filters=UniverseCandidateFilters(exclude_non_voting=True),
            output=output,
        )

        text = output.getvalue()
        assert exit_code == 0
        assert "session" in text
        assert "session-e" in text
        assert "f-base" in text
    finally:
        shutil.rmtree(directory, ignore_errors=True)
