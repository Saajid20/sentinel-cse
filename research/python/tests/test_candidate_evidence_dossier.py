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

from candidate_evidence_dossier import (  # noqa: E402
    build_candidate_evidence_dossier,
    parse_args,
    run_candidate_evidence_dossier,
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
    company_name: str | None = None,
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
    if company_name is not None:
        snapshot["metadata"] = {"companyName": company_name}
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


def build_replay_export(
    input_path: str,
    *,
    session_id: str,
    total_snapshots: int,
    unique_tickers: int,
    signals_generated: int,
    per_ticker_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "inputPath": input_path,
        "source": "atrad-full-watch-equity",
        "totalSnapshotsLoaded": total_snapshots,
        "replayedSnapshots": total_snapshots,
        "uniqueTickers": unique_tickers,
        "signalsGenerated": signals_generated,
        "aggregateReplayDiagnostics": {
            "likelyBlockers": ["momentum trigger blocked"],
        },
        "thresholdSummary": {},
        "perTickerConditionDiagnostics": per_ticker_rows,
    }


def build_replay_ticker_row(
    ticker: str,
    *,
    snapshots: int,
    history_pass: int,
    strategy_ready: int,
    spread_pass: int,
    vwap_available: int,
    price_above_vwap: int,
    first_high_available: int,
    momentum_pass: int,
    volume_ratio_available: int,
    volume_ratio_pass: int,
    imbalance_available: int,
    imbalance_pass: int,
    signals: int,
    top_blockers: list[str],
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "snapshots": snapshots,
        "historyPass": history_pass,
        "strategyReady": strategy_ready,
        "spreadPass": spread_pass,
        "vwapAvailable": vwap_available,
        "priceAboveVwap": price_above_vwap,
        "firstHighAvailable": first_high_available,
        "momentumPass": momentum_pass,
        "volumeRatioAvailable": volume_ratio_available,
        "volumeRatioPass": volume_ratio_pass,
        "imbalanceAvailable": imbalance_available,
        "imbalancePass": imbalance_pass,
        "signals": signals,
        "topBlockers": top_blockers,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_root_happy_path_prints_all_sections() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"),
                    build_snapshot("KEEP.N0000", 2, company_name="Keep PLC"),
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
                    )
                ],
            ),
        )
        write_json(
            runtime_root / "session-a" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=2,
                unique_tickers=1,
                signals_generated=1,
                per_ticker_rows=[
                    build_replay_ticker_row(
                        "KEEP.N0000",
                        snapshots=2,
                        history_pass=1,
                        strategy_ready=0,
                        spread_pass=2,
                        vwap_available=2,
                        price_above_vwap=1,
                        first_high_available=1,
                        momentum_pass=1,
                        volume_ratio_available=1,
                        volume_ratio_pass=1,
                        imbalance_available=2,
                        imbalance_pass=1,
                        signals=1,
                        top_blockers=["momentum trigger blocked"],
                    )
                ],
            ),
        )

        output = io.StringIO()
        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
            output=output,
        )
        text = output.getvalue()

        assert "Dossier header" in text
        assert "Session evidence table" in text
        assert "Filtered signal evidence" in text
        assert "Variant interpretation" in text
        assert "Blocker context" in text
        assert "R10/R11 readiness placeholders" in text
        assert "Safety note" in text
        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )
        assert report.blocker_rows[0].signals == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_repeated_tier_a_ticker_renders_manual_review_status() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_specs = [
            (
                "session-a",
                "store_fallback_scroll",
                [500, 505],
                [build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
            (
                "session-b",
                "store_reconstructed",
                [25, 25],
                [build_variant_row("imbalance-disabled-diagnostic", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        ]
        for name, scan_mode, coverage, variant_rows in session_specs:
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[
                        build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"),
                        build_snapshot("KEEP.N0000", 2, company_name="Keep PLC"),
                    ],
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
                    variant_rows=variant_rows,
                ),
            )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert report.header.evidence_tier == "Tier A"
        assert report.header.review_status == "MANUAL_REVIEW"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_surviving_filtered_evidence_renders_insufficient_evidence_dossier() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC")],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=1,
                unique_tickers=1,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=1, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(min_snapshots=2),
        )

        assert report.header.review_status == "INSUFFICIENT_EVIDENCE"
        assert any("did not survive active research filters" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_variant_export_warns_and_keeps_partial_dossier() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=2,
                unique_tickers=1,
                signals_generated=0,
                per_ticker_rows=[],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert any("missing variant export" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_unreadable_raw_session_json_warns_and_renders_runtime_only_rows() -> None:
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
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        )
        write_json(
            runtime_root / "missing" / "replay-diagnostics.json",
            build_replay_export(
                str(missing_session_path),
                session_id="missing-id",
                total_snapshots=2,
                unique_tickers=1,
                signals_generated=1,
                per_ticker_rows=[
                    build_replay_ticker_row(
                        "KEEP.N0000",
                        snapshots=2,
                        history_pass=1,
                        strategy_ready=0,
                        spread_pass=2,
                        vwap_available=2,
                        price_above_vwap=1,
                        first_high_available=1,
                        momentum_pass=1,
                        volume_ratio_available=1,
                        volume_ratio_pass=1,
                        imbalance_available=2,
                        imbalance_pass=1,
                        signals=1,
                        top_blockers=["momentum trigger blocked"],
                    )
                ],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert any("session JSON unreadable" in warning for warning in report.warnings)
        assert report.session_rows[0].quality_classification == "unknown"
        assert report.filtered_signal_rows[0].filtered_ticker_count is None
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_replay_export_renders_blocker_context_as_na() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
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
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert report.blocker_rows[0].snapshots is None
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_expected_variants_do_not_crash() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
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
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert len(report.filtered_signal_rows) == 1
        assert report.header.baseline_count == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_partial_truncated_signal_ticker_counts_mark_lower_bound() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "partial.json"
        write_json(
            session_path,
            build_session_payload(
                "partial-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
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

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert "lower-bound" in report.filtered_signal_rows[0].notes
        assert any("lower bounds" in warning for warning in report.warnings)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_deterministic_ordering_for_session_rows() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        for name in ("session-z", "session-a"):
            session_path = directory / f"{name}.json"
            write_json(
                session_path,
                build_session_payload(
                    f"{name}-id",
                    snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
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
                    variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=1, signal_ticker_counts=[("KEEP.N0000", 1)])],
                ),
            )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert [row.session_stem for row in report.session_rows] == ["session-a", "session-z"]
        assert [row.session_stem for row in report.filtered_signal_rows] == ["session-a", "session-z"]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_per_session_raw_vs_filtered_counts_render_correctly() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"), build_snapshot("KEEP.N0000", 2, company_name="Keep PLC")],
                diagnostics=build_diagnostics_rows("store_fallback_scroll", [500, 505]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=2,
                unique_tickers=2,
                variant_rows=[build_variant_row("baseline", replayed_snapshots=2, signals_generated=3, signal_ticker_counts=[("KEEP.N0000", 1), ("OTHER.N0000", 2)])],
            ),
        )

        report = build_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
        )

        assert report.filtered_signal_rows[0].raw_variant_signal_count == 3
        assert report.filtered_signal_rows[0].filtered_ticker_count == 1
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cli_parses_markdown_output_flag() -> None:
    args = parse_args(["--ticker", "KEEP.N0000", "--markdown-output", "out/report.md"])

    assert args.ticker == "KEEP.N0000"
    assert args.markdown_output == "out/report.md"


def test_no_markdown_file_is_written_without_flag() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"),
                    build_snapshot("KEEP.N0000", 2, company_name="Keep PLC"),
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
                    )
                ],
            ),
        )

        output = io.StringIO()
        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
            output=output,
        )

        assert not any(directory.rglob("*.md"))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_markdown_output_writes_expected_sections_and_keeps_terminal_output() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        markdown_path = directory / ".runtime-pipeline" / "candidate-dossiers" / "KEEP.N0000.md"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"),
                    build_snapshot("KEEP.N0000", 2, company_name="Keep PLC"),
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
                    )
                ],
            ),
        )
        write_json(
            runtime_root / "session-a" / "replay-diagnostics.json",
            build_replay_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=2,
                unique_tickers=1,
                signals_generated=1,
                per_ticker_rows=[
                    build_replay_ticker_row(
                        "KEEP.N0000",
                        snapshots=2,
                        history_pass=1,
                        strategy_ready=0,
                        spread_pass=2,
                        vwap_available=2,
                        price_above_vwap=1,
                        first_high_available=1,
                        momentum_pass=1,
                        volume_ratio_available=1,
                        volume_ratio_pass=1,
                        imbalance_available=2,
                        imbalance_pass=1,
                        signals=1,
                        top_blockers=["momentum trigger blocked"],
                    )
                ],
            ),
        )

        output = io.StringIO()
        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
            markdown_output=markdown_path,
            output=output,
        )

        text = output.getvalue()
        markdown = markdown_path.read_text(encoding="utf-8")

        assert "Dossier header" in text
        assert "# Candidate Evidence Dossier - KEEP.N0000" in markdown
        assert "## Safety notice" in markdown
        assert "## Dossier header" in markdown
        assert "## Session evidence table" in markdown
        assert "## Filtered signal evidence table" in markdown
        assert "## Variant interpretation" in markdown
        assert "## Blocker context table" in markdown
        assert "## R10/R11 readiness placeholders" in markdown
        assert "## Warnings / limitations" in markdown
        assert "## Generated-from/runtime source notes" in markdown
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_markdown_output_creates_parent_directory_and_includes_safety_notice() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        markdown_path = directory / "nested" / "dossiers" / "KEEP.N0000.md"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[
                    build_snapshot("KEEP.N0000", 1, company_name="Keep PLC"),
                    build_snapshot("KEEP.N0000", 2, company_name="Keep PLC"),
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
                    )
                ],
            ),
        )

        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
            markdown_output=markdown_path,
            output=io.StringIO(),
        )

        markdown = markdown_path.read_text(encoding="utf-8")
        assert markdown_path.is_file()
        assert "research-only" in markdown
        assert "not financial advice" in markdown
        assert "not a buy/sell/hold recommendation" in markdown
        assert "not live execution guidance" in markdown
        assert "Human review is required." in markdown
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_markdown_output_contains_no_uppercase_trading_action_language() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        markdown_path = directory / "KEEP.N0000.md"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC")],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=1,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=1,
                        signals_generated=1,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    )
                ],
            ),
        )

        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(),
            markdown_output=markdown_path,
            output=io.StringIO(),
        )

        markdown = markdown_path.read_text(encoding="utf-8")
        for token in ("BUY", "SELL", "HOLD", "ENTRY", "EXIT", "TRADE"):
            assert token not in markdown
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_surviving_evidence_still_exports_markdown_dossier() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = directory / "session-a.json"
        markdown_path = directory / "KEEP.N0000.md"
        write_json(
            session_path,
            build_session_payload(
                "session-a-id",
                snapshots=[build_snapshot("KEEP.N0000", 1, company_name="Keep PLC")],
                diagnostics=build_diagnostics_rows("store_reconstructed", [25]),
            ),
        )
        write_json(
            runtime_root / "session-a" / "variant-comparison.json",
            build_variant_export(
                str(session_path),
                session_id="session-a-id",
                total_snapshots=1,
                unique_tickers=1,
                variant_rows=[
                    build_variant_row(
                        "baseline",
                        replayed_snapshots=1,
                        signals_generated=1,
                        signal_ticker_counts=[("KEEP.N0000", 1)],
                    )
                ],
            ),
        )

        run_candidate_evidence_dossier(
            "KEEP.N0000",
            runtime_root,
            [],
            UniverseCandidateFilters(min_snapshots=2),
            markdown_output=markdown_path,
            output=io.StringIO(),
        )

        markdown = markdown_path.read_text(encoding="utf-8")
        assert "INSUFFICIENT_EVIDENCE" in markdown
        assert "ticker did not survive active research filters" in markdown
    finally:
        shutil.rmtree(directory, ignore_errors=True)
