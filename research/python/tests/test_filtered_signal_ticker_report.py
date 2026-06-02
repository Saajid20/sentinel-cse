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

from filtered_signal_ticker_report import (  # noqa: E402
    build_filtered_signal_ticker_report,
    run_filtered_signal_ticker_report,
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


def test_runtime_root_happy_path_prints_aggregate_and_detail_sections() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1),
                    build_snapshot("KEEP.N0000", 2),
                ],
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

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())
        output = io.StringIO()
        run_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters(), output=output)
        text = output.getvalue()

        assert len(report.aggregate_rows) == 1
        assert len(report.detail_rows) == 2
        assert "Aggregate surviving tickers" in text
        assert "Per-session surviving ticker detail" in text
        assert "KEEP.N0000" in text
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_repeated_ticker_across_sessions_rolls_up_counts_and_variants() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        for name, counts in (("session-a", [("baseline", 1), ("imbalance-disabled-diagnostic", 2)]), ("session-b", [("baseline", 1)])):
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[build_snapshot("KEEP.N0000", 1), build_snapshot("KEEP.N0000", 2)],
                    diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
                ),
            )
            write_json(
                runtime_root / name / "variant-comparison.json",
                build_variant_export(
                    str(session_path),
                    session_id=f"{name}-id",
                    total_snapshots=2,
                    unique_tickers=1,
                    variant_rows=[
                        build_variant_row(
                            variant_name,
                            replayed_snapshots=2,
                            signals_generated=count,
                            signal_ticker_counts=[("KEEP.N0000", count)],
                        )
                        for variant_name, count in counts
                    ],
                ),
            )

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())

        row = report.aggregate_rows[0]
        assert row.ticker == "KEEP.N0000"
        assert row.session_count == 2
        assert row.variants == ("base", "imb-off")
        assert row.total_count == 4
        assert row.baseline_count == 2
        assert row.imbalance_disabled_count == 2
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_partial_coverage_only_detection_marks_notes() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "partial.json"
        write_json(
            session_path,
            build_session_payload(
                "partial-id",
                snapshots=[build_snapshot("ONLY.N0000", 1), build_snapshot("ONLY.N0000", 2)],
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
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=1,
                        signal_ticker_counts=[("ONLY.N0000", 1)],
                    )
                ],
            ),
        )

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())

        assert report.aggregate_rows[0].coverage_label == "partial-coverage"
        assert report.aggregate_rows[0].notes == "partial-coverage-only"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_exclude_non_voting_and_pattern_remove_surviving_rows() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "filtered.json"
        write_json(
            session_path,
            build_session_payload(
                "filtered-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1),
                    build_snapshot("DROP.X0000", 1),
                    build_snapshot("WARR.U0000", 1),
                ],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25]),
            ),
        )
        write_json(
            runtime_root / "filtered" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="filtered-id",
                total_snapshots=3,
                unique_tickers=3,
                variant_rows=[
                    build_variant_row(
                        "volume-and-imbalance-disabled-diagnostic",
                        replayed_snapshots=3,
                        signals_generated=3,
                        signal_ticker_counts=[
                            ("KEEP.N0000", 1),
                            ("DROP.X0000", 1),
                            ("WARR.U0000", 1),
                        ],
                    )
                ],
            ),
        )

        report = build_filtered_signal_ticker_report(
            runtime_root,
            [],
            UniverseCandidateFilters(exclude_non_voting=True, exclude_patterns=[".u0000"]),
        )

        assert [row.ticker for row in report.aggregate_rows] == ["KEEP.N0000"]
        assert [row.ticker for row in report.detail_rows] == ["KEEP.N0000"]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_metric_filter_exclusion_removes_tickers_that_fail_thresholds() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "metrics.json"
        write_json(
            session_path,
            build_session_payload(
                "metrics-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, volume=12_000, turnover=25_000, best_bid=9.9, best_ask=10.0),
                    build_snapshot("KEEP.N0000", 2, volume=15_000, turnover=26_000, best_bid=10.0, best_ask=10.1),
                    build_snapshot("SNAP.N0000", 1, volume=12_000, turnover=25_000, best_bid=9.9, best_ask=10.0),
                    build_snapshot("COVR.N0000", 1, volume=12_000, turnover=25_000, best_bid=9.9, best_ask=10.0),
                    build_snapshot("COVR.N0000", 2, volume=15_000, turnover=26_000, best_bid=None, best_ask=None),
                    build_snapshot("SPRD.N0000", 1, volume=12_000, turnover=25_000, best_bid=8.0, best_ask=10.0),
                    build_snapshot("SPRD.N0000", 2, volume=15_000, turnover=26_000, best_bid=8.0, best_ask=10.0),
                    build_snapshot("TURN.N0000", 1, volume=12_000, turnover=5_000, best_bid=9.9, best_ask=10.0),
                    build_snapshot("TURN.N0000", 2, volume=15_000, turnover=6_000, best_bid=10.0, best_ask=10.1),
                    build_snapshot("VOLM.N0000", 1, volume=5_000, turnover=25_000, best_bid=9.9, best_ask=10.0),
                    build_snapshot("VOLM.N0000", 2, volume=6_000, turnover=26_000, best_bid=10.0, best_ask=10.1),
                ],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25, 25]),
            ),
        )
        write_json(
            runtime_root / "metrics" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="metrics-id",
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

        report = build_filtered_signal_ticker_report(
            runtime_root,
            [],
            UniverseCandidateFilters(
                min_snapshots=2,
                min_bid_ask_coverage=0.8,
                max_median_spread=1.5,
                min_latest_turnover=10_000,
                min_max_volume=10_000,
            ),
        )

        assert [row.ticker for row in report.aggregate_rows] == ["KEEP.N0000"]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_unreadable_raw_session_json_with_filters_active_prints_warning_and_skips_rows() -> None:
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
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=1,
                        signal_ticker_counts=[("MISS.N0000", 1)],
                    )
                ],
            ),
        )

        report = build_filtered_signal_ticker_report(
            runtime_root,
            [],
            UniverseCandidateFilters(exclude_non_voting=True),
        )

        assert report.aggregate_rows == []
        assert report.detail_rows == []
        assert any("session JSON unreadable" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_expected_variants_do_not_crash() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "present.json"
        write_json(
            session_path,
            build_session_payload(
                "present-id",
                snapshots=[build_snapshot("KEEP.N0000", 1), build_snapshot("KEEP.N0000", 2)],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "present" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="present-id",
                total_snapshots=2,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=1,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    )
                ],
            ),
        )

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())

        assert len(report.aggregate_rows) == 1
        assert report.aggregate_rows[0].baseline_count == 1
        assert report.aggregate_rows[0].volume_ratio_disabled_count == 0
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_truncated_partial_export_prints_warning_and_keeps_lower_bound_rows() -> None:
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
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=2,
                        signals_generated=3,
                        unique_signal_tickers=3,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    )
                ],
            ),
        )

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())

        assert len(report.detail_rows) == 1
        assert report.detail_rows[0].count == 1
        assert any("lower bounds" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_deterministic_ordering_for_aggregate_and_detail_rows() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        for name in ("session-z", "session-a"):
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[
                        build_snapshot("BETA.N0000", 1),
                        build_snapshot("ALFA.N0000", 2),
                    ],
                    diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
                ),
            )
            write_json(
                runtime_root / name / "variant-comparison.json",
                build_variant_export(
                    str(session_path),
                    session_id=f"{name}-id",
                    total_snapshots=2,
                    unique_tickers=2,
                    variant_rows=[
                        build_variant_row(
                            "baseline",
                            replayed_snapshots=2,
                            signals_generated=2,
                            signal_ticker_counts=[("BETA.N0000", 1), ("ALFA.N0000", 1)],
                        )
                    ],
                ),
            )

        report = build_filtered_signal_ticker_report(runtime_root, [], UniverseCandidateFilters())

        assert [row.ticker for row in report.aggregate_rows] == ["ALFA.N0000", "BETA.N0000"]
        assert [
            (row.session_stem, row.variant_label, row.ticker) for row in report.detail_rows
        ] == [
            ("session-a", "base", "ALFA.N0000"),
            ("session-a", "base", "BETA.N0000"),
            ("session-z", "base", "ALFA.N0000"),
            ("session-z", "base", "BETA.N0000"),
        ]
    finally:
        shutil.rmtree(directory, ignore_errors=True)
