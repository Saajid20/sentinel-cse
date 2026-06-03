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

DEFAULT_SOURCE_TYPES = (
    "CSE_DISCLOSURE",
    "CSE_ANNOUNCEMENT",
    "CSE_FINANCIAL_DISCLOSURE",
)
REQUIRED_VALIDATIONS = (
    "validate_candidate_context_request",
    "source_integrity_check",
    "R10_schema_validation",
    "policy_consistency_guard",
    "unsafe_trading_language_guard",
    "human_review_required",
)
_COMPANY_SUFFIXES = {"PLC", "LIMITED", "LTD"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a dry-run R10 candidate context query plan from an existing "
            "CandidateContextRequest JSON file. This does not execute R10, "
            "retrieval, network calls, or downstream review."
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


def _dedupe_keep_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def simplify_company_name(company_name: str | None) -> str | None:
    if company_name is None:
        return None
    tokens = company_name.strip().split()
    while tokens:
        normalized = tokens[-1].rstrip(".,)").upper()
        if normalized not in _COMPANY_SUFFIXES:
            break
        tokens.pop()
    simplified = " ".join(tokens).strip()
    if not simplified or simplified == company_name.strip():
        return None
    return simplified


def build_query_terms(request: CandidateContextRequest) -> list[str]:
    ticker = request.ticker
    ticker_root = ticker.split(".", maxsplit=1)[0].strip()
    company_name = request.company_name
    simplified_company_name = simplify_company_name(company_name)
    return _dedupe_keep_order(
        [
            ticker,
            ticker_root,
            company_name or "",
            simplified_company_name or "",
        ]
    )


def render_request_plan(path: Path, request: CandidateContextRequest) -> str:
    requested_reviews = ", ".join(item.value for item in request.requested_reviews)
    warnings = request.warnings or ["none"]
    query_terms = build_query_terms(request)
    session_stems = request.artifact_refs.session_stems or []
    dossier_markdown_path = request.artifact_refs.dossier_markdown_path or "n/a"

    lines = [
        "R10 candidate context dry-run query plan",
        "",
        "Validated candidate request summary",
        f"- input path: {path}",
        f"- ticker: {request.ticker}",
        f"- company_name: {request.company_name or 'n/a'}",
        f"- evidence_tier: {request.evidence_tier.value}",
        f"- review_status: {request.review_status.value}",
        f"- requested_reviews: {requested_reviews}",
        f"- total_filtered_count: {request.technical_summary.total_filtered_count}",
        f"- first_session: {request.technical_summary.first_session or 'n/a'}",
        f"- last_session: {request.technical_summary.last_session or 'n/a'}",
        "- warnings:",
    ]
    lines.extend(f"  - {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "Proposed R10 source intent",
            *[f"- {source_type}" for source_type in DEFAULT_SOURCE_TYPES],
            "- CBSL macro context is deferred unless an explicit macro-relevance rule exists.",
            "",
            "Proposed query terms",
            *[f"- {term}" for term in query_terms],
            "",
            "Required validations",
            *[f"- {validation}" for validation in REQUIRED_VALIDATIONS],
            "",
            "Artifact refs",
            f"- runtime_root: {request.artifact_refs.runtime_root}",
            "- session_stems:",
        ]
    )
    if session_stems:
        lines.extend(f"  - {session_stem}" for session_stem in session_stems)
    else:
        lines.append("  - none")
    lines.extend(
        [
            f"- dossier_markdown_path: {dossier_markdown_path}",
            "",
            "Safety note",
            "- This is retrieval intent only.",
            "- Actual evidence must come from R10-controlled CSE/CBSL source documents.",
            "- Technical candidate evidence is not a disclosure/fundamental source.",
            "- This is not financial advice.",
            "- This is not live execution guidance.",
            "- Human review is required.",
            "- Later R10 output remains SUPPORT / BLOCK / MANUAL_REVIEW / NO_EFFECT only.",
        ]
    )
    return "\n".join(lines)


def print_fail_summary(path: Path, reasons: list[str]) -> None:
    print("R10 candidate context dry-run query plan: FAIL")
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

    print(render_request_plan(input_path, request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
