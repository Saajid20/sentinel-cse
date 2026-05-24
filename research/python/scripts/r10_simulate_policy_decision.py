from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.policy import (  # noqa: E402
    StrategyCandidateType,
    TechnicalSignalCandidate,
    evaluate_r10_policy,
)
from sentinel_research.agents.reports import R10AnalysisReport  # noqa: E402


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _parse_iso_timestamp(value: str, *, field_name: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO timestamp {value!r}. Expected ISO-8601 format."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(f"{field_name} must be timezone-aware")
    return parsed


def _parse_detected_at(value: str) -> datetime:
    return _parse_iso_timestamp(value, field_name="detected-at")


def _parse_generated_at(value: str) -> datetime:
    return _parse_iso_timestamp(value, field_name="generated-at")


def _parse_metadata(entries: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for entry in entries:
        key, separator, raw_value = entry.partition("=")
        normalized_key = key.strip()
        if not separator or not normalized_key:
            raise ValueError(
                f"Invalid metadata entry {entry!r}. Expected KEY=VALUE format."
            )
        metadata[normalized_key] = raw_value.strip()
    return metadata


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulate an R10 policy decision from a saved R10AnalysisReport."
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path to an existing R10AnalysisReport JSON file.",
    )
    parser.add_argument(
        "--candidate-id",
        required=True,
        type=_non_empty_value("candidate_id"),
        help="Simulation candidate ID.",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        type=_non_empty_value("ticker"),
        help="Ticker symbol, for example JKH.N0000.",
    )
    parser.add_argument(
        "--strategy-candidate-type",
        required=True,
        choices=[candidate_type.value for candidate_type in StrategyCandidateType],
        help="Simulation-only technical candidate type.",
    )
    parser.add_argument(
        "--detected-at",
        type=_parse_detected_at,
        help="Optional ISO-8601 timestamp for when the simulated candidate was detected.",
    )
    parser.add_argument(
        "--generated-at",
        type=_parse_generated_at,
        help="Optional ISO-8601 timestamp for the policy decision.",
    )
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Optional metadata entry in KEY=VALUE form. May be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to save the R10PolicyDecision JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        report_path = Path(args.report).expanduser()
        if not report_path.exists() or not report_path.is_file():
            raise ValueError(f"R10AnalysisReport path does not exist: {report_path}")

        report = R10AnalysisReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        candidate = TechnicalSignalCandidate(
            candidate_id=args.candidate_id,
            ticker=args.ticker,
            strategy_candidate_type=args.strategy_candidate_type,
            detected_at=args.detected_at or datetime.now(UTC),
            metadata=_parse_metadata(args.metadata),
        )
        decision = evaluate_r10_policy(
            candidate,
            report,
            generated_at=args.generated_at or datetime.now(UTC),
        )

        print("R10 Policy Simulation Decision")
        print(f"report_id: {decision.r10_report_id}")
        print(f"candidate_id: {decision.candidate_id}")
        print(f"ticker: {decision.ticker}")
        print(f"r10_policy: {decision.r10_policy.value}")
        print(f"manual_review_required: {decision.manual_review_required}")
        print(f"reason_codes: {decision.reason_codes}")
        print(f"normalized_catalyst_tags: {decision.normalized_catalyst_tags}")
        print(decision.model_dump_json(indent=2))

        if args.output:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                decision.model_dump_json(indent=2),
                encoding="utf-8",
                newline="\n",
            )
            print(f"output path: {output_path}")

        return 0
    except (ValueError, ValidationError) as error:
        print(f"R10 policy simulation failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 policy simulation failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
