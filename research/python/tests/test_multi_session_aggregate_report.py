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


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_session_payload(
    session_id: str,
    ticker: str,
    *,
    diagnostics: list[dict[str, object]],
    ticks_attempted: int,
    snapshot_count: int,
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "startedAt": "2026-06-02T04:00:00.000Z",
        "endedAt": "2026-06-02T04:30:00.000Z",
        "source": "atrad-full-watch-equity",
        "mode": "read-only-local-recording",
        "snapshots": [
            {
                "ticker": ticker,
                "timestamp": index,
                "lastPrice": 10.0 + index,
                "bestBid": 9.9 + index,
                "bestAsk": 10.1 + index,
                "volume": 1000 + index,
                "totalTurnover": 10000 + index,
            }
            for index in range(snapshot_count)
        ],
        "diagnostics": diagnostics,
        "totals": {
            "ticksAttempted": ticks_attempted,
            "usableSnapshots": snapshot_count,
            "quarantinedSnapshots": 0,
            "rejectedSnapshots": 0,
        },
    }


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


def build_replay_export(input_path: str, *, session_id: str, unique_tickers: int, total_snapshots: int) -> dict[str, object]:
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


def build_variant_export(
    input_path: str,
    *,
    session_id: str,
    total_snapshots: int,
    unique_tickers: int,
    variant_names: list[tuple[str, int]],
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
        "variants": [
            {
                "variantName": name,
                "diagnosticOnly": name != "baseline",
                "description": name,
                "parameterOverrides": {},
                "runtimeMode": "SHADOW",
                "replayedSnapshots": total_snapshots,
                "signalsGenerated": count,
                "uniqueSignalTickers": count,
                "generatedStrategies": [],
                "signalTickerCounts": [],
            }
            for name, count in variant_names
        ],
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_root_happy_path_reads_exports_and_raw_session() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "data" / "session-a.json"
        diagnostics = build_diagnostics_rows(
            scan_mode="store_fallback_scroll",
            unique_tickers=[500, 505, 510, 515, 520],
        )
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                "ALFA.N0000",
                diagnostics=diagnostics,
                ticks_attempted=5,
                snapshot_count=5,
            ),
        )
        session_dir = runtime_root / "session-a"
        write_json(
            session_dir / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-a-id",
                unique_tickers=1,
                total_snapshots=5,
            ),
        )
        write_json(
            session_dir / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=5,
                unique_tickers=1,
                variant_names=[
                    ("baseline", 1),
                    ("volume-ratio-disabled-diagnostic", 2),
                    ("imbalance-disabled-diagnostic", 3),
                    ("volume-and-imbalance-disabled-diagnostic", 4),
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
        diagnostics = (
            build_diagnostics_rows(scan_mode="store_reconstructed", unique_tickers=[25, 25, 26])
            + build_diagnostics_rows(scan_mode="store_fallback_scroll", unique_tickers=[24, 25])
        )
        write_json(
            session_path,
            build_session_payload(
                "session-b-id",
                "BETA.N0000",
                diagnostics=diagnostics,
                ticks_attempted=5,
                snapshot_count=5,
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
        session_dir = runtime_root / "session-c"
        write_json(
            session_dir / "replay-diagnostics.json",
            build_replay_export(
                str(missing_session_path),
                session_id="session-c-id",
                unique_tickers=96,
                total_snapshots=595,
            ),
        )
        write_json(
            session_dir / "variant-comparison.json",
            build_variant_export(
                str(missing_session_path),
                session_id="session-c-id",
                total_snapshots=595,
                unique_tickers=96,
                variant_names=[("baseline", 4)],
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


def test_missing_expected_variants_render_na_without_crashing() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-d.json"
        write_json(
            session_path,
            build_session_payload(
                "session-d-id",
                "DELTA.N0000",
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[450, 455, 460],
                ),
                ticks_attempted=3,
                snapshot_count=3,
            ),
        )
        session_dir = runtime_root / "session-d"
        write_json(
            session_dir / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-d-id",
                unique_tickers=1,
                total_snapshots=3,
            ),
        )
        write_json(
            session_dir / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-d-id",
                total_snapshots=3,
                unique_tickers=1,
                variant_names=[("baseline", 2)],
            ),
        )

        table = format_rows_table(build_aggregate_rows(runtime_root, []))

        assert "session-d" in table
        assert " 2 " in table
        assert "n/a" in table
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_session_rows_are_sorted_deterministically() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        for name in ("session-z", "session-a", "session-m"):
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    "ALFA.N0000",
                    diagnostics=build_diagnostics_rows(
                        scan_mode="store_fallback_scroll",
                        unique_tickers=[400, 401],
                    ),
                    ticks_attempted=2,
                    snapshot_count=2,
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

        assert [row.session_stem for row in rows] == ["session-a", "session-m", "session-z"]
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
                "EPSI.N0000",
                diagnostics=build_diagnostics_rows(
                    scan_mode="store_fallback_scroll",
                    unique_tickers=[500, 505],
                ),
                ticks_attempted=2,
                snapshot_count=2,
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
        exit_code = run_multi_session_aggregate_report(runtime_root, [], output=output)

        text = output.getvalue()
        assert exit_code == 0
        assert "session" in text
        assert "session-e" in text
    finally:
        shutil.rmtree(directory, ignore_errors=True)
