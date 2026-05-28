from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from multi_session_validation import (  # noqa: E402
    RUNTIME_REMINDER,
    build_replay_diagnostics_command,
    build_session_runtime_paths,
    build_variant_comparison_command,
    flatten_inputs,
    run_multi_session_validation,
)


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def build_session_payload(session_id: str, ticker: str) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "startedAt": "2026-05-26T05:47:22.000Z",
        "endedAt": "2026-05-26T06:17:22.000Z",
        "source": "atrad-full-watch-equity",
        "mode": "read-only-local-recording",
        "snapshots": [
            {
                "ticker": ticker,
                "timestamp": 1,
                "lastPrice": 10.0,
                "bestBid": 9.9,
                "bestAsk": 10.1,
                "volume": 1000,
                "totalTurnover": 10000,
            }
        ],
        "diagnostics": [
            {
                "marketState": "OPEN",
                "scanMode": "store_fallback_scroll",
                "fullGridScan": True,
                "uniqueTickers": 1,
            }
        ],
        "totals": {
            "ticksAttempted": 1,
            "usableSnapshots": 1,
            "quarantinedSnapshots": 0,
            "rejectedSnapshots": 0,
        },
    }


def write_session_file(directory: Path, name: str, payload: dict[str, object]) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def build_replay_diagnostics_export(input_path: str) -> dict[str, object]:
    return {
        "sessionId": "diagnostics-session",
        "inputPath": input_path,
        "source": "atrad-full-watch-equity",
        "totalSnapshotsLoaded": 1,
        "replayedSnapshots": 1,
        "uniqueTickers": 1,
        "signalsGenerated": 0,
        "aggregateReplayDiagnostics": {
            "snapshotsProcessed": 1,
            "enrichedSnapshots": 1,
            "spreadBlockedCount": 0,
            "volumeBlockedCount": 0,
            "imbalanceBlockedCount": 0,
            "vwapMissingCount": 0,
            "firstFiveMinuteHighMissingCount": 0,
            "priceNotAboveVwapCount": 0,
            "priceNotAboveMomentumTriggerCount": 0,
            "insufficientHistoryCount": 0,
            "strategyReadySnapshotCount": 1,
            "likelyBlockers": [],
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
                "snapshots": 1,
                "historyPass": 1,
                "strategyReady": 1,
                "spreadPass": 1,
                "vwapAvailable": 1,
                "priceAboveVwap": 1,
                "firstHighAvailable": 1,
                "momentumPass": 1,
                "volumeRatioAvailable": 1,
                "volumeRatioPass": 1,
                "imbalanceAvailable": 1,
                "imbalancePass": 1,
                "signals": 0,
                "topBlockers": [],
            }
        ],
    }


def build_variant_comparison_export(input_path: str) -> dict[str, object]:
    return {
        "sessionId": "variant-session",
        "inputPath": input_path,
        "source": "atrad-full-watch-equity",
        "startedAt": "2026-05-26T05:47:22.000Z",
        "endedAt": "2026-05-26T06:17:22.000Z",
        "totalSnapshotsLoaded": 1,
        "uniqueTickers": 1,
        "topSignalTickerLimit": 10,
        "variants": [
            {
                "variantName": "baseline",
                "diagnosticOnly": False,
                "description": "Default Opening Momentum detector parameters.",
                "parameterOverrides": {},
                "runtimeMode": "SHADOW",
                "replayedSnapshots": 1,
                "signalsGenerated": 0,
                "uniqueSignalTickers": 0,
                "generatedStrategies": [],
                "signalTickerCounts": [],
            }
        ],
    }


class FakeCommandRunner:
    def __init__(self, *, fail_on_replay: bool = False) -> None:
        self.fail_on_replay = fail_on_replay
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, command: list[str], cwd: Path) -> None:
        self.calls.append((command, cwd))
        if command[:2] == ["pnpm", "atrad:replay-session"]:
            if self.fail_on_replay:
                raise RuntimeError("replay export failed")
            output_path = Path(command[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            input_path = command[4]
            output_path.write_text(
                json.dumps(build_replay_diagnostics_export(input_path)),
                encoding="utf-8",
            )
            return

        if command[:2] == ["pnpm", "tsx"]:
            output_path = Path(command[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            input_path = command[4]
            output_path.write_text(
                json.dumps(build_variant_comparison_export(input_path)),
                encoding="utf-8",
            )
            return

        raise AssertionError(f"Unexpected command: {command}")


def test_multiple_input_session_paths_are_accepted_and_ordered_deterministically() -> None:
    values = [["b.json", "a.json"], ["c.json"]]

    flattened = flatten_inputs(values)

    assert flattened == [Path("b.json"), Path("a.json"), Path("c.json")]


def test_runtime_output_paths_are_generated_under_runtime_root() -> None:
    runtime_root = Path(".runtime-pipeline") / "multi-session-validation"
    session_path = Path(r"C:\sessions\atrad-session-20260526-054722.json")

    paths = build_session_runtime_paths(session_path, runtime_root)

    assert paths.session_dir == runtime_root / "atrad-session-20260526-054722"
    assert paths.replay_diagnostics_path == paths.session_dir / "replay-diagnostics.json"
    assert paths.variant_comparison_path == paths.session_dir / "variant-comparison.json"


def test_subprocess_command_is_built_correctly_for_replay_diagnostics_export() -> None:
    command = build_replay_diagnostics_command(
        Path(r"C:\sessions\session.json"),
        Path(r".runtime-pipeline\multi-session-validation\session\replay-diagnostics.json"),
    )

    assert command == [
        "pnpm",
        "atrad:replay-session",
        "--",
        "--input",
        r"C:\sessions\session.json",
        "--condition-diagnostics",
        "--diagnostics-json-output",
        r".runtime-pipeline\multi-session-validation\session\replay-diagnostics.json",
    ]


def test_subprocess_command_is_built_correctly_for_variant_comparison_export() -> None:
    command = build_variant_comparison_command(
        Path(r"C:\sessions\session.json"),
        Path(r".runtime-pipeline\multi-session-validation\session\variant-comparison.json"),
        20,
    )

    assert command == [
        "pnpm",
        "tsx",
        "scripts/manualATradReplayStrategyVariants.ts",
        "--input",
        r"C:\sessions\session.json",
        "--top",
        "20",
        "--variant-json-output",
        r".runtime-pipeline\multi-session-validation\session\variant-comparison.json",
    ]


def test_input_session_files_are_not_modified(capsys: pytest.CaptureFixture[str]) -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = write_session_file(
            directory,
            "session-a.json",
            build_session_payload("session-a", "ALFA.N0000"),
        )
        before = session_path.read_text(encoding="utf-8")

        exit_code = run_multi_session_validation(
            input_paths=[session_path],
            runtime_dir=runtime_root,
            top=5,
            repo_root=directory,
            command_runner=FakeCommandRunner(),
        )

        assert exit_code == 0
        assert session_path.read_text(encoding="utf-8") == before
        assert "Session result: SUCCESS" in capsys.readouterr().out
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_failed_subprocess_stage_produces_clear_per_session_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = write_session_file(
            directory,
            "session-a.json",
            build_session_payload("session-a", "ALFA.N0000"),
        )

        exit_code = run_multi_session_validation(
            input_paths=[session_path],
            runtime_dir=runtime_root,
            top=5,
            repo_root=directory,
            command_runner=FakeCommandRunner(fail_on_replay=True),
        )
        output = capsys.readouterr().out

        assert exit_code == 1
        assert "Session result: FAILED at replay-diagnostics-export" in output
        assert "replay export failed" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_script_returns_non_zero_if_any_session_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        valid_session = write_session_file(
            directory,
            "valid.json",
            build_session_payload("valid-session", "ALFA.N0000"),
        )
        invalid_session = directory / "invalid.json"
        invalid_session.write_text("{not-json", encoding="utf-8")

        exit_code = run_multi_session_validation(
            input_paths=[valid_session, invalid_session],
            runtime_dir=runtime_root,
            top=5,
            repo_root=directory,
            command_runner=FakeCommandRunner(),
        )
        output = capsys.readouterr().out

        assert exit_code == 1
        assert "successful sessions: 1" in output
        assert "failed sessions: 1" in output
        assert "invalid.json: failed at session-summary" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_terminal_output_includes_session_headings_and_runtime_artifact_reminder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = write_session_file(
            directory,
            "session-a.json",
            build_session_payload("session-a", "ALFA.N0000"),
        )

        run_multi_session_validation(
            input_paths=[session_path],
            runtime_dir=runtime_root,
            top=5,
            repo_root=directory,
            command_runner=FakeCommandRunner(),
        )
        output = capsys.readouterr().out

        assert "=== Session: session-a.json ===" in output
        assert "Sentinel-CSE multi-session validation workflow" in output
        assert RUNTIME_REMINDER in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_writes_outside_provided_runtime_directory() -> None:
    directory = make_temp_dir()
    try:
        runtime_root = directory / ".runtime-pipeline" / "multi-session-validation"
        session_path = write_session_file(
            directory,
            "session-a.json",
            build_session_payload("session-a", "ALFA.N0000"),
        )
        runner = FakeCommandRunner()

        exit_code = run_multi_session_validation(
            input_paths=[session_path],
            runtime_dir=runtime_root,
            top=5,
            repo_root=directory,
            command_runner=runner,
        )

        assert exit_code == 0
        for command, _ in runner.calls:
            output_path = Path(command[-1]).resolve()
            output_path.relative_to(runtime_root.resolve())
    finally:
        shutil.rmtree(directory, ignore_errors=True)
