from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "variant_comparison_report.py"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from variant_comparison_report import (  # noqa: E402
    build_variant_comparison_report,
    format_variant_comparison_report,
    load_variant_comparison,
)


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_variant(
    name: str,
    *,
    diagnostic_only: bool,
    signals_generated: int = 0,
    unique_signal_tickers: int = 0,
    parameter_overrides: dict[str, object] | None = None,
    generated_strategies: list[str] | None = None,
    signal_ticker_counts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "variantName": name,
        "diagnosticOnly": diagnostic_only,
        "description": f"{name} description",
        "parameterOverrides": parameter_overrides or {},
        "runtimeMode": "SHADOW",
        "replayedSnapshots": 5680,
        "signalsGenerated": signals_generated,
        "uniqueSignalTickers": unique_signal_tickers,
        "generatedStrategies": generated_strategies or [],
        "signalTickerCounts": signal_ticker_counts or [],
    }


def build_comparison(variants: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sessionId": "atrad-session-20260526-054837",
        "inputPath": r".runtime-pipeline\variant-comparison-20260526-054722.json",
        "source": "atrad-full-watch-equity",
        "startedAt": "2026-05-26T05:48:37.706Z",
        "endedAt": "2026-05-26T05:58:28.131Z",
        "totalSnapshotsLoaded": 5680,
        "uniqueTickers": 215,
        "topSignalTickerLimit": 20,
        "variants": variants,
    }


def test_valid_variant_comparison_json_loads() -> None:
    directory = make_temp_dir()
    try:
        comparison_path = directory / "comparison.json"
        comparison_path.write_text(
            json.dumps(build_comparison([build_variant("baseline", diagnostic_only=False)])),
            encoding="utf-8",
        )

        comparison = load_variant_comparison(comparison_path)

        assert comparison["sessionId"] == "atrad-session-20260526-054837"
        assert comparison["source"] == "atrad-full-watch-equity"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_session_header_fields_render_correctly() -> None:
    report = build_variant_comparison_report(
        build_comparison([build_variant("baseline", diagnostic_only=False)])
    )
    text = format_variant_comparison_report(report)

    assert "sessionId: atrad-session-20260526-054837" in text
    assert r"inputPath: .runtime-pipeline\variant-comparison-20260526-054722.json" in text
    assert "source: atrad-full-watch-equity" in text
    assert "totalSnapshotsLoaded: 5,680" in text
    assert "uniqueTickers: 215" in text
    assert "topSignalTickerLimit: 20" in text
    assert "variantCount: 1" in text


def test_per_variant_signals_and_unique_ticker_counts_render_correctly() -> None:
    report = build_variant_comparison_report(
        build_comparison(
            [
                build_variant("baseline", diagnostic_only=False, signals_generated=0),
                build_variant(
                    "imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    signals_generated=2,
                    unique_signal_tickers=2,
                ),
            ]
        )
    )
    text = format_variant_comparison_report(report)

    assert "variant: baseline" in text
    assert "variant: imbalance-disabled-diagnostic" in text
    assert "- signalsGenerated: 2" in text
    assert "- uniqueSignalTickers: 2" in text


def test_diagnostic_only_flag_and_parameter_overrides_render_correctly() -> None:
    report = build_variant_comparison_report(
        build_comparison(
            [
                build_variant(
                    "imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    parameter_overrides={"orderBookImbalanceThreshold": -1},
                )
            ]
        )
    )
    text = format_variant_comparison_report(report)

    assert "- diagnosticOnly: yes" in text
    assert "- parameterOverrides: orderBookImbalanceThreshold=-1" in text


def test_generated_strategies_and_signal_ticker_counts_render_correctly() -> None:
    report = build_variant_comparison_report(
        build_comparison(
            [
                build_variant(
                    "imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    signals_generated=2,
                    unique_signal_tickers=2,
                    generated_strategies=["CSE_OPENING_MOMENTUM_V1"],
                    signal_ticker_counts=[
                        {"ticker": "LITE.N0000", "count": 1},
                        {"ticker": "SEYB.X0000", "count": 1},
                    ],
                )
            ]
        )
    )
    text = format_variant_comparison_report(report)

    assert "- generatedStrategies: CSE_OPENING_MOMENTUM_V1" in text
    assert "- top signalTickerCounts: LITE.N0000:1, SEYB.X0000:1" in text


def test_variants_that_changed_signal_count_versus_baseline_are_identified_correctly() -> None:
    report = build_variant_comparison_report(
        build_comparison(
            [
                build_variant("baseline", diagnostic_only=False, signals_generated=0),
                build_variant(
                    "imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    signals_generated=2,
                ),
                build_variant(
                    "volume-and-imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    signals_generated=2,
                ),
            ]
        )
    )
    text = format_variant_comparison_report(report)

    assert "- baseline: 0 unchanged" in text
    assert "- imbalance-disabled-diagnostic: +2 changed" in text
    assert "- volume-and-imbalance-disabled-diagnostic: +2 changed" in text
    assert (
        "- changed variants: imbalance-disabled-diagnostic, volume-and-imbalance-disabled-diagnostic"
        in text
    )


def test_warning_appears_when_diagnostic_only_variant_generates_signals() -> None:
    report = build_variant_comparison_report(
        build_comparison(
            [
                build_variant("baseline", diagnostic_only=False, signals_generated=0),
                build_variant(
                    "imbalance-disabled-diagnostic",
                    diagnostic_only=True,
                    signals_generated=2,
                ),
            ]
        )
    )
    text = format_variant_comparison_report(report)

    assert (
        "- offline research only; diagnostic variants are not production recommendations"
        in text
    )
    assert (
        "- diagnostic-only variant imbalance-disabled-diagnostic generated 2 signals"
        in text
    )


def test_top_limits_displayed_signal_ticker_rows() -> None:
    directory = make_temp_dir()
    try:
        comparison_path = directory / "comparison.json"
        comparison_path.write_text(
            json.dumps(
                build_comparison(
                    [
                        build_variant(
                            "imbalance-disabled-diagnostic",
                            diagnostic_only=True,
                            signals_generated=3,
                            unique_signal_tickers=3,
                            signal_ticker_counts=[
                                {"ticker": "ALFA.N0000", "count": 2},
                                {"ticker": "BETA.N0000", "count": 1},
                                {"ticker": "CALT.N0000", "count": 1},
                            ],
                        )
                    ]
                )
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--input", str(comparison_path), "--top", "2"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0
        assert "display top signalTickerCounts: 2" in completed.stdout
        assert "ALFA.N0000:2, BETA.N0000:1" in completed.stdout
        assert "CALT.N0000:1" not in completed.stdout
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_optional_fields_show_unavailable_instead_of_crashing() -> None:
    report = build_variant_comparison_report(
        {
            "sessionId": "minimal-variant-comparison",
            "variants": [
                {
                    "variantName": "baseline",
                }
            ],
        }
    )
    text = format_variant_comparison_report(report)

    assert "inputPath: unavailable" in text
    assert "source: unavailable" in text
    assert "totalSnapshotsLoaded: unavailable" in text
    assert "uniqueTickers: unavailable" in text
    assert "- diagnosticOnly: unavailable" in text
    assert "- parameterOverrides: default" in text
    assert "- generatedStrategies: none" in text
    assert "- top signalTickerCounts: none" in text
