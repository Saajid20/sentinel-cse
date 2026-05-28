from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from strategy_blocker_report import (
    build_strategy_blocker_report,
    format_strategy_blocker_report,
    load_replay_diagnostics,
)
from summarize_session import (
    SessionFormatError,
    format_terminal_summary,
    load_session,
    summarize_session,
)
from universe_candidate_report import (
    build_universe_candidate_report,
    format_universe_candidate_report,
)
from variant_comparison_report import (
    build_variant_comparison_report,
    format_variant_comparison_report,
    load_variant_comparison,
)

DEFAULT_RUNTIME_DIR = Path(".runtime-pipeline") / "multi-session-validation"
RUNTIME_REMINDER = (
    "Reminder: .runtime-pipeline artifacts are runtime outputs and must not be committed."
)


class MultiSessionValidationError(RuntimeError):
    """Raised when one validation stage fails for a session."""


CommandRunner = Callable[[list[str], Path], None]


@dataclass(frozen=True)
class SessionRuntimePaths:
    session_dir: Path
    replay_diagnostics_path: Path
    variant_comparison_path: Path


@dataclass(frozen=True)
class SessionValidationResult:
    session_path: Path
    ok: bool
    failed_stage: str | None = None
    error_message: str | None = None
    runtime_paths: SessionRuntimePaths | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Sentinel-CSE offline validation workflow across multiple recorded ATrad sessions."
    )
    parser.add_argument(
        "--input",
        action="append",
        nargs="+",
        required=True,
        help="Path to a recorded ATrad session JSON file. Repeat or provide multiple values.",
    )
    parser.add_argument(
        "--runtime-dir",
        default=str(DEFAULT_RUNTIME_DIR),
        help="Runtime output root for replay diagnostics and variant comparison exports.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top-N limit passed to report sections and variant signal ticker display.",
    )
    return parser.parse_args(argv)


def flatten_inputs(values: Iterable[list[str]]) -> list[Path]:
    return [Path(item) for group in values for item in group]


def build_session_runtime_paths(session_path: Path, runtime_dir: Path) -> SessionRuntimePaths:
    session_dir = runtime_dir / session_path.stem
    replay_diagnostics_path = session_dir / "replay-diagnostics.json"
    variant_comparison_path = session_dir / "variant-comparison.json"
    ensure_path_within_root(session_dir, runtime_dir)
    ensure_path_within_root(replay_diagnostics_path, runtime_dir)
    ensure_path_within_root(variant_comparison_path, runtime_dir)
    return SessionRuntimePaths(
        session_dir=session_dir,
        replay_diagnostics_path=replay_diagnostics_path,
        variant_comparison_path=variant_comparison_path,
    )


def ensure_path_within_root(path: Path, runtime_dir: Path) -> None:
    resolved_root = runtime_dir.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise MultiSessionValidationError(
            f"Refusing to use runtime path outside {runtime_dir}: {path}"
        ) from error


def build_replay_diagnostics_command(
    session_path: Path,
    replay_diagnostics_path: Path,
) -> list[str]:
    return [
        "pnpm",
        "atrad:replay-session",
        "--",
        "--input",
        str(session_path),
        "--condition-diagnostics",
        "--diagnostics-json-output",
        str(replay_diagnostics_path),
    ]


def build_variant_comparison_command(
    session_path: Path,
    variant_comparison_path: Path,
    top: int,
) -> list[str]:
    return [
        "pnpm",
        "tsx",
        "scripts/manualATradReplayStrategyVariants.ts",
        "--input",
        str(session_path),
        "--top",
        str(max(top, 0)),
        "--variant-json-output",
        str(variant_comparison_path),
    ]


def run_subprocess(command: list[str], cwd: Path) -> None:
    actual_command = list(command)
    if sys.platform == "win32" and actual_command and actual_command[0] == "pnpm":
        actual_command[0] = "pnpm.cmd"
    completed = subprocess.run(
        actual_command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return

    output_parts = [part.strip() for part in (completed.stdout, completed.stderr) if part.strip()]
    detail = " | ".join(output_parts) if output_parts else f"exit code {completed.returncode}"
    raise MultiSessionValidationError(
        f"Command failed: {' '.join(command)}. {detail}"
    )


def print_section(title: str, body: str) -> None:
    print(title)
    print(body)
    print()


def validate_session_file(
    session_path: Path,
    runtime_dir: Path,
    top: int,
    repo_root: Path,
    command_runner: CommandRunner,
) -> SessionValidationResult:
    runtime_paths = build_session_runtime_paths(session_path, runtime_dir)
    safe_top = max(top, 0)

    print(f"=== Session: {session_path.name} ===")
    print(f"input path: {session_path}")
    print(f"runtime directory: {runtime_paths.session_dir}")
    print(RUNTIME_REMINDER)
    print()

    try:
        stage = "session-summary"
        session = load_session(session_path)
        session_summary = summarize_session(session, top=safe_top)
        print_section("Session summary / quality:", format_terminal_summary(session_summary))

        stage = "universe-candidate-report"
        universe_report = build_universe_candidate_report(session, top=safe_top)
        print_section("Universe candidate report:", format_universe_candidate_report(universe_report))

        stage = "replay-diagnostics-export"
        command_runner(
            build_replay_diagnostics_command(session_path, runtime_paths.replay_diagnostics_path),
            repo_root,
        )
        print(f"Replay diagnostics export: {runtime_paths.replay_diagnostics_path}")
        print()

        stage = "strategy-blocker-report"
        replay_diagnostics = load_replay_diagnostics(runtime_paths.replay_diagnostics_path)
        blocker_report = build_strategy_blocker_report(replay_diagnostics, top=safe_top)
        print_section("Strategy blocker report:", format_strategy_blocker_report(blocker_report))

        stage = "variant-comparison-export"
        command_runner(
            build_variant_comparison_command(
                session_path,
                runtime_paths.variant_comparison_path,
                safe_top,
            ),
            repo_root,
        )
        print(f"Variant comparison export: {runtime_paths.variant_comparison_path}")
        print()

        stage = "variant-comparison-report"
        variant_comparison = load_variant_comparison(runtime_paths.variant_comparison_path)
        comparison_report = build_variant_comparison_report(variant_comparison, top=safe_top)
        print_section("Variant comparison report:", format_variant_comparison_report(comparison_report))

        print("Session result: SUCCESS")
        print()
        return SessionValidationResult(
            session_path=session_path,
            ok=True,
            runtime_paths=runtime_paths,
        )
    except Exception as error:
        print(f"Session result: FAILED at {stage}")
        print(f"error: {error}")
        print()
        return SessionValidationResult(
            session_path=session_path,
            ok=False,
            failed_stage=stage,
            error_message=str(error),
            runtime_paths=runtime_paths,
        )


def run_multi_session_validation(
    input_paths: list[Path],
    runtime_dir: Path,
    top: int,
    repo_root: Path,
    command_runner: CommandRunner = run_subprocess,
) -> int:
    runtime_root = runtime_dir.resolve()
    session_paths = [Path(path) for path in input_paths]

    print("Sentinel-CSE multi-session validation workflow")
    print(f"session count: {len(session_paths)}")
    print(f"runtime root: {runtime_root}")
    print(RUNTIME_REMINDER)
    print()

    results = [
        validate_session_file(
            session_path=session_path,
            runtime_dir=runtime_root,
            top=top,
            repo_root=repo_root,
            command_runner=command_runner,
        )
        for session_path in session_paths
    ]

    success_count = sum(1 for result in results if result.ok)
    failure_count = len(results) - success_count
    print("Overall result:")
    print(f"- successful sessions: {success_count}")
    print(f"- failed sessions: {failure_count}")
    if failure_count:
        for result in results:
            if not result.ok:
                print(
                    f"- {result.session_path.name}: failed at {result.failed_stage}"
                    f" ({result.error_message})"
                )
    print(f"- runtime root: {runtime_root}")
    print(f"- reminder: {RUNTIME_REMINDER}")

    return 0 if failure_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_paths = flatten_inputs(args.input)
    return run_multi_session_validation(
        input_paths=input_paths,
        runtime_dir=Path(args.runtime_dir),
        top=max(args.top, 0),
        repo_root=Path(__file__).resolve().parents[3],
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
