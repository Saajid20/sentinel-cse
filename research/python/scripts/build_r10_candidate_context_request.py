from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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
CBSL_DEFERRED_REASON = (
    "CBSL macro context is deferred unless an explicit macro-relevance rule exists."
)


@dataclass(frozen=True)
class R10CandidateQueryPlan:
    candidate_request_path: str
    ticker: str
    company_name: str | None
    evidence_tier: str
    review_status: str
    requested_reviews: tuple[str, ...]
    total_filtered_count: int
    first_session: str | None
    last_session: str | None
    warnings: tuple[str, ...]
    requested_source_types: tuple[str, ...]
    query_terms: tuple[str, ...]
    cbsl_context_included: bool
    cbsl_context_reason: str
    required_validations: tuple[str, ...]
    runtime_root: str
    session_stems: tuple[str, ...]
    dossier_markdown_path: str | None


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
    parser.add_argument(
        "--json-output",
        help=(
            "Optional dry-run query plan JSON export path, for example "
            ".runtime-pipeline/r10-candidate-query-plans/PKME.N0000.json. "
            "Runtime artifacts should not be committed."
        ),
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


def build_r10_candidate_query_plan(
    path: Path,
    request: CandidateContextRequest,
) -> R10CandidateQueryPlan:
    return R10CandidateQueryPlan(
        candidate_request_path=str(path),
        ticker=request.ticker,
        company_name=request.company_name,
        evidence_tier=request.evidence_tier.value,
        review_status=request.review_status.value,
        requested_reviews=tuple(item.value for item in request.requested_reviews),
        total_filtered_count=request.technical_summary.total_filtered_count,
        first_session=request.technical_summary.first_session,
        last_session=request.technical_summary.last_session,
        warnings=tuple(request.warnings),
        requested_source_types=tuple(DEFAULT_SOURCE_TYPES),
        query_terms=tuple(build_query_terms(request)),
        cbsl_context_included=False,
        cbsl_context_reason=CBSL_DEFERRED_REASON,
        required_validations=tuple(REQUIRED_VALIDATIONS),
        runtime_root=request.artifact_refs.runtime_root,
        session_stems=tuple(request.artifact_refs.session_stems),
        dossier_markdown_path=request.artifact_refs.dossier_markdown_path,
    )


def render_r10_candidate_query_plan(plan: R10CandidateQueryPlan) -> str:
    requested_reviews = ", ".join(plan.requested_reviews)
    warnings = plan.warnings or ("none",)
    dossier_markdown_path = plan.dossier_markdown_path or "n/a"

    lines = [
        "R10 candidate context dry-run query plan",
        "",
        "Validated candidate request summary",
        f"- input path: {plan.candidate_request_path}",
        f"- ticker: {plan.ticker}",
        f"- company_name: {plan.company_name or 'n/a'}",
        f"- evidence_tier: {plan.evidence_tier}",
        f"- review_status: {plan.review_status}",
        f"- requested_reviews: {requested_reviews}",
        f"- total_filtered_count: {plan.total_filtered_count}",
        f"- first_session: {plan.first_session or 'n/a'}",
        f"- last_session: {plan.last_session or 'n/a'}",
        "- warnings:",
    ]
    lines.extend(f"  - {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "Proposed R10 source intent",
            *[f"- {source_type}" for source_type in plan.requested_source_types],
            f"- {plan.cbsl_context_reason}",
            "",
            "Proposed query terms",
            *[f"- {term}" for term in plan.query_terms],
            "",
            "Required validations",
            *[f"- {validation}" for validation in plan.required_validations],
            "",
            "Artifact refs",
            f"- runtime_root: {plan.runtime_root}",
            "- session_stems:",
        ]
    )
    if plan.session_stems:
        lines.extend(f"  - {session_stem}" for session_stem in plan.session_stems)
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


def build_r10_candidate_query_plan_json(
    plan: R10CandidateQueryPlan,
) -> dict[str, object]:
    return {
        "schema_version": "r10-candidate-query-plan/v0.1",
        "candidate_request_path": plan.candidate_request_path,
        "ticker": plan.ticker,
        "company_name": plan.company_name,
        "evidence_tier": plan.evidence_tier,
        "review_status": plan.review_status,
        "requested_reviews": list(plan.requested_reviews),
        "requested_source_types": list(plan.requested_source_types),
        "query_terms": list(plan.query_terms),
        "cbsl_context": {
            "included": plan.cbsl_context_included,
            "reason": plan.cbsl_context_reason,
        },
        "required_validations": list(plan.required_validations),
        "artifact_refs": {
            "runtime_root": plan.runtime_root,
            "session_stems": list(plan.session_stems),
            "dossier_markdown_path": plan.dossier_markdown_path,
        },
        "safety": {
            "retrieval_intent_only": True,
            "no_r10_execution": True,
            "no_network": True,
            "technical_evidence_is_not_source_evidence": True,
            "not_financial_advice": True,
            "not_live_execution_guidance": True,
            "human_review_required": True,
        },
    }


def write_r10_candidate_query_plan_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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

    plan = build_r10_candidate_query_plan(input_path, request)
    if args.json_output:
        write_r10_candidate_query_plan_json(
            Path(args.json_output).expanduser(),
            build_r10_candidate_query_plan_json(plan),
        )
    print(render_r10_candidate_query_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
