from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "strategy_blocker_report.py"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from strategy_blocker_report import (  # noqa: E402
    build_strategy_blocker_report,
    format_strategy_blocker_report,
    load_replay_diagnostics,
)


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_ticker_row(
    ticker: str,
    *,
    snapshots: int = 10,
    history_pass: int | None = None,
    strategy_ready: int = 0,
    spread_pass: int | None = None,
    vwap_available: int | None = None,
    price_above_vwap: int | None = None,
    first_high_available: int | None = None,
    momentum_pass: int = 0,
    volume_ratio_available: int | None = None,
    volume_ratio_pass: int = 0,
    imbalance_available: int | None = None,
    imbalance_pass: int | None = None,
    signals: int = 0,
    top_blockers: list[str] | None = None,
) -> dict[str, object]:
    resolved_history_pass = history_pass if history_pass is not None else max(snapshots - 1, 0)
    resolved_spread_pass = spread_pass if spread_pass is not None else snapshots
    resolved_vwap_available = vwap_available if vwap_available is not None else snapshots
    resolved_price_above_vwap = price_above_vwap if price_above_vwap is not None else snapshots
    resolved_first_high_available = (
        first_high_available if first_high_available is not None else max(snapshots - 1, 0)
    )
    resolved_volume_ratio_available = (
        volume_ratio_available if volume_ratio_available is not None else max(snapshots - 1, 0)
    )
    resolved_imbalance_available = imbalance_available if imbalance_available is not None else snapshots
    resolved_imbalance_pass = imbalance_pass if imbalance_pass is not None else resolved_imbalance_available

    return {
        "ticker": ticker,
        "snapshots": snapshots,
        "historyPass": resolved_history_pass,
        "strategyReady": strategy_ready,
        "spreadPass": resolved_spread_pass,
        "vwapAvailable": resolved_vwap_available,
        "priceAboveVwap": resolved_price_above_vwap,
        "firstHighAvailable": resolved_first_high_available,
        "momentumPass": momentum_pass,
        "volumeRatioAvailable": resolved_volume_ratio_available,
        "volumeRatioPass": volume_ratio_pass,
        "imbalanceAvailable": resolved_imbalance_available,
        "imbalancePass": resolved_imbalance_pass,
        "signals": signals,
        "topBlockers": top_blockers or [],
    }


def build_diagnostics(
    *,
    per_ticker: list[dict[str, object]] | None = None,
    aggregate: dict[str, object] | None = None,
    threshold: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "sessionId": "atrad-session-20260526-054837",
        "inputPath": r".runtime-pipeline\replay-diagnostics-20260526-054722.json",
        "source": "atrad-full-watch-equity",
        "totalSnapshotsLoaded": 5_680,
        "replayedSnapshots": 5_680,
        "uniqueTickers": 215,
        "signalsGenerated": 0,
        "aggregateReplayDiagnostics": aggregate
        or {
            "snapshotsProcessed": 5_680,
            "enrichedSnapshots": 5_680,
            "spreadBlockedCount": 1_902,
            "volumeBlockedCount": 5_680,
            "imbalanceBlockedCount": 3_446,
            "vwapMissingCount": 428,
            "firstFiveMinuteHighMissingCount": 215,
            "priceNotAboveVwapCount": 1_529,
            "priceNotAboveMomentumTriggerCount": 5_457,
            "insufficientHistoryCount": 215,
            "strategyReadySnapshotCount": 1_286,
            "likelyBlockers": [
                "insufficient time-series history",
                "volume ratio unavailable",
                "VWAP missing",
            ],
        },
        "thresholdSummary": threshold
        or {
            "maxSpreadPercent": 1.5,
            "minimumVolumeRatio": 2,
            "minimumImbalance": 0,
            "momentumTriggerBasis": "lastPrice > first5MinHighEstimate derived from prior session high",
        },
        **({"perTickerConditionDiagnostics": per_ticker} if per_ticker is not None else {}),
    }


def test_valid_replay_diagnostics_json_loads() -> None:
    directory = make_temp_dir()
    try:
        diagnostics_path = directory / "diagnostics.json"
        diagnostics_path.write_text(json.dumps(build_diagnostics()), encoding="utf-8")

        diagnostics = load_replay_diagnostics(diagnostics_path)

        assert diagnostics["sessionId"] == "atrad-session-20260526-054837"
        assert diagnostics["source"] == "atrad-full-watch-equity"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_aggregate_blocker_counts_are_displayed_from_json() -> None:
    report = build_strategy_blocker_report(build_diagnostics())
    text = format_strategy_blocker_report(report)

    assert "spreadBlockedCount: 1,902" in text
    assert "volumeBlockedCount: 5,680" in text
    assert "strategyReadySnapshotCount: 1,286" in text
    assert "likelyBlockers: insufficient time-series history, volume ratio unavailable, VWAP missing" in text


def test_threshold_summary_is_displayed() -> None:
    report = build_strategy_blocker_report(build_diagnostics())
    text = format_strategy_blocker_report(report)

    assert "maxSpreadPercent: 1.5" in text
    assert "minimumVolumeRatio: 2" in text
    assert "minimumImbalance: 0" in text
    assert "momentumTriggerBasis: lastPrice > first5MinHighEstimate derived from prior session high" in text


def test_missing_per_ticker_condition_diagnostics_does_not_crash() -> None:
    report = build_strategy_blocker_report(build_diagnostics(per_ticker=None))
    text = format_strategy_blocker_report(report)

    assert report.per_ticker_available is False
    assert "Condition funnel:" in text
    assert "snapshots: unavailable" in text
    assert "Top blocker patterns:" in text
    assert "- unavailable" in text


def test_top_blockers_are_aggregated_correctly() -> None:
    report = build_strategy_blocker_report(
        build_diagnostics(
            per_ticker=[
                build_ticker_row("MOMO.N0000", top_blockers=["momentum trigger blocked", "price below VWAP"]),
                build_ticker_row("VOLU.N0000", top_blockers=["volume ratio blocked", "momentum trigger blocked"]),
                build_ticker_row("SPRD.N0000", top_blockers=["volume ratio blocked", "spread blocked"]),
            ]
        )
    )

    assert report.top_blocker_patterns[:4] == [
        ("momentum trigger blocked", 2),
        ("volume ratio blocked", 2),
        ("price below VWAP", 1),
        ("spread blocked", 1),
    ]


def test_fails_mainly_momentum_candidates_are_identified() -> None:
    report = build_strategy_blocker_report(
        build_diagnostics(
            per_ticker=[
                build_ticker_row(
                    "MOMO.N0000",
                    momentum_pass=0,
                    top_blockers=["momentum trigger blocked"],
                ),
                build_ticker_row(
                    "MISS.N0000",
                    spread_pass=8,
                    momentum_pass=0,
                    top_blockers=["momentum trigger blocked"],
                ),
            ]
        )
    )

    assert [candidate.ticker for candidate in report.momentum_candidates] == ["MOMO.N0000"]


def test_fails_mainly_volume_ratio_candidates_are_identified() -> None:
    report = build_strategy_blocker_report(
        build_diagnostics(
            per_ticker=[
                build_ticker_row(
                    "VOLU.N0000",
                    momentum_pass=4,
                    volume_ratio_pass=0,
                    top_blockers=["volume ratio blocked"],
                ),
                build_ticker_row(
                    "ZERO.N0000",
                    momentum_pass=0,
                    volume_ratio_pass=0,
                    top_blockers=["volume ratio blocked"],
                ),
            ]
        )
    )

    assert [candidate.ticker for candidate in report.volume_ratio_candidates] == ["VOLU.N0000"]


def test_top_limits_ticker_sections() -> None:
    directory = make_temp_dir()
    try:
        diagnostics_path = directory / "diagnostics.json"
        diagnostics_path.write_text(
            json.dumps(
                build_diagnostics(
                    per_ticker=[
                        build_ticker_row("MOMO1.N0000", snapshots=12, momentum_pass=0, top_blockers=["momentum trigger blocked"]),
                        build_ticker_row("MOMO2.N0000", snapshots=11, momentum_pass=0, top_blockers=["momentum trigger blocked"]),
                        build_ticker_row("VOLU1.N0000", snapshots=12, momentum_pass=3, volume_ratio_pass=0, top_blockers=["volume ratio blocked"]),
                        build_ticker_row("VOLU2.N0000", snapshots=11, momentum_pass=2, volume_ratio_pass=0, top_blockers=["volume ratio blocked"]),
                    ]
                )
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--input", str(diagnostics_path), "--top", "1"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0
        assert "top limit: 1" in completed.stdout
        assert "MOMO1.N0000" in completed.stdout
        assert "MOMO2.N0000" not in completed.stdout
        assert "VOLU1.N0000" in completed.stdout
        assert "VOLU2.N0000" not in completed.stdout
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_optional_fields_show_unavailable() -> None:
    report = build_strategy_blocker_report(
        {
            "sessionId": "minimal-diagnostics",
            "aggregateReplayDiagnostics": {},
            "perTickerConditionDiagnostics": [
                {
                    "ticker": "MISS.N0000",
                    "topBlockers": [],
                }
            ],
        }
    )
    text = format_strategy_blocker_report(report)

    assert "inputPath: unavailable" in text
    assert "source: unavailable" in text
    assert "replayedSnapshots: unavailable" in text
    assert "maxSpreadPercent: unavailable" in text
    assert "spreadBlockedCount: unavailable" in text
    assert "snapshots: unavailable" in text
