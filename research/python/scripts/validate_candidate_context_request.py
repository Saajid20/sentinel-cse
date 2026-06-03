from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.context_bridge import CandidateContextRequest  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an existing CandidateContextRequest JSON file. "
            "This is validation-only and does not call downstream review layers."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an existing CandidateContextRequest JSON file.",
    )
    return parser


def load_request_payload(path: Path) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        raise ValueError(f"missing file: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"unreadable file: {path} ({error})") from error

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"malformed JSON: {error.msg} at line {error.lineno} column {error.colno}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")

    return payload


def format_validation_errors(error: ValidationError) -> list[str]:
    lines: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
        message = item.get("msg", "validation error")
        lines.append(f"{location}: {message}")
    return lines or ["validation error"]


def print_pass_summary(path: Path, request: CandidateContextRequest) -> None:
    requested_reviews = ", ".join(item.value for item in request.requested_reviews)
    print("CandidateContextRequest validation: PASS")
    print(f"input: {path}")
    print(f"ticker: {request.ticker}")
    print(f"schema_version: {request.schema_version}")
    print(f"review_status: {request.review_status.value}")
    print(f"evidence_tier: {request.evidence_tier.value}")
    print(f"requested_reviews: {requested_reviews}")
    print("safety: verified")


def print_fail_summary(path: Path, reasons: list[str]) -> None:
    print("CandidateContextRequest validation: FAIL")
    print(f"input: {path}")
    print("reason:")
    for reason in reasons:
        print(f"* {reason}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input).expanduser()

    try:
        payload = load_request_payload(input_path)
        request = CandidateContextRequest.model_validate(payload)
    except ValidationError as error:
        print_fail_summary(input_path, format_validation_errors(error))
        return 2
    except ValueError as error:
        print_fail_summary(input_path, [str(error)])
        return 2

    print_pass_summary(input_path, request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
