from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA_VERSION = "r10-candidate-query-plan/v0.1"
ALLOWED_SOURCE_TYPES = {
    "CSE_DISCLOSURE",
    "CSE_ANNOUNCEMENT",
    "CSE_FINANCIAL_DISCLOSURE",
    "CBSL_CONTEXT",
}
REQUIRED_SOURCE_TYPES = {
    "CSE_DISCLOSURE",
    "CSE_ANNOUNCEMENT",
    "CSE_FINANCIAL_DISCLOSURE",
}
REQUIRED_VALIDATIONS = {
    "validate_candidate_context_request",
    "source_integrity_check",
    "R10_schema_validation",
    "policy_consistency_guard",
    "unsafe_trading_language_guard",
    "human_review_required",
}
REQUIRED_SAFETY_FLAGS = (
    "retrieval_intent_only",
    "no_r10_execution",
    "no_network",
    "technical_evidence_is_not_source_evidence",
    "not_financial_advice",
    "not_live_execution_guidance",
    "human_review_required",
)
_UNSAFE_PATTERN = re.compile(r"\b(?:buy|sell|hold|entry|exit|trade)\b", re.IGNORECASE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an existing R10 candidate query-plan JSON file. "
            "This is validation-only and does not execute R10, retrieval, or network calls."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an existing R10 candidate query-plan JSON file.",
    )
    return parser


def load_json_payload(path: Path) -> dict[str, object]:
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


def _non_empty_str(value: object, field_name: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_name}: must be a non-empty string")
        return None
    return value.strip()


def _string_list(value: object, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field_name}: must be a non-empty list")
        return []

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field_name}.{index}: must be a non-empty string")
            continue
        normalized.append(item.strip())
    return normalized


def _check_unsafe_language(value: str, field_name: str, errors: list[str]) -> None:
    if _UNSAFE_PATTERN.search(value):
        errors.append(f"{field_name}: contains unsafe trading recommendation language")


def validate_query_plan(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []

    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        errors.append(f'schema_version: must be "{SCHEMA_VERSION}"')

    _non_empty_str(payload.get("candidate_request_path"), "candidate_request_path", errors)
    _non_empty_str(payload.get("ticker"), "ticker", errors)

    requested_source_types = _string_list(
        payload.get("requested_source_types"),
        "requested_source_types",
        errors,
    )
    invalid_source_types = [
        item for item in requested_source_types if item not in ALLOWED_SOURCE_TYPES
    ]
    for item in invalid_source_types:
        errors.append(f"requested_source_types: invalid source type {item}")
    missing_source_types = [
        item for item in REQUIRED_SOURCE_TYPES if item not in requested_source_types
    ]
    for item in missing_source_types:
        errors.append(f"requested_source_types: missing required source type {item}")

    cbsl_context = payload.get("cbsl_context")
    cbsl_included = False
    if not isinstance(cbsl_context, dict):
        errors.append("cbsl_context: must be an object")
    else:
        included = cbsl_context.get("included")
        if not isinstance(included, bool):
            errors.append("cbsl_context.included: must be a boolean")
        else:
            cbsl_included = included
        reason = _non_empty_str(cbsl_context.get("reason"), "cbsl_context.reason", errors)
        if reason is not None:
            _check_unsafe_language(reason, "cbsl_context.reason", errors)

    if not cbsl_included and "CBSL_CONTEXT" in requested_source_types:
        errors.append(
            "requested_source_types: CBSL_CONTEXT must not appear when cbsl_context.included is false"
        )

    query_terms = _string_list(payload.get("query_terms"), "query_terms", errors)
    if not query_terms:
        errors.append("query_terms: must contain at least one non-empty string")

    required_validations = _string_list(
        payload.get("required_validations"),
        "required_validations",
        errors,
    )
    missing_validations = [
        item for item in REQUIRED_VALIDATIONS if item not in required_validations
    ]
    for item in missing_validations:
        errors.append(f"required_validations: missing required validation {item}")

    artifact_refs = payload.get("artifact_refs")
    if not isinstance(artifact_refs, dict):
        errors.append("artifact_refs: must be an object")
    else:
        _non_empty_str(artifact_refs.get("runtime_root"), "artifact_refs.runtime_root", errors)
        session_stems = artifact_refs.get("session_stems")
        if not isinstance(session_stems, list):
            errors.append("artifact_refs.session_stems: must be a list")
        else:
            for index, item in enumerate(session_stems):
                if not isinstance(item, str) or not item.strip():
                    errors.append(
                        f"artifact_refs.session_stems.{index}: must be a non-empty string"
                    )

    safety = payload.get("safety")
    if not isinstance(safety, dict):
        errors.append("safety: must be an object")
    else:
        for field_name in REQUIRED_SAFETY_FLAGS:
            if safety.get(field_name) is not True:
                errors.append(f"safety.{field_name}: must be true")

    return errors


def print_pass_summary(path: Path, payload: dict[str, object]) -> None:
    requested_source_types = payload.get("requested_source_types", [])
    cbsl_context = payload.get("cbsl_context", {})
    included = bool(cbsl_context.get("included")) if isinstance(cbsl_context, dict) else False
    cbsl_status = "included" if included else "deferred"
    query_terms = payload.get("query_terms", [])
    query_term_count = len(query_terms) if isinstance(query_terms, list) else 0

    print("R10 candidate query plan validation: PASS")
    print(f"input: {path}")
    print(f"ticker: {payload.get('ticker')}")
    print(f"schema_version: {payload.get('schema_version')}")
    print(f"requested_source_types: {', '.join(requested_source_types)}")
    print(f"query_terms: {query_term_count}")
    print(f"cbsl_context: {cbsl_status}")
    print("safety: verified")


def print_fail_summary(path: Path, reasons: list[str]) -> None:
    print("R10 candidate query plan validation: FAIL")
    print(f"input: {path}")
    print("reason:")
    for reason in reasons:
        print(f"* {reason}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input).expanduser()

    try:
        payload = load_json_payload(input_path)
    except ValueError as error:
        print_fail_summary(input_path, [str(error)])
        return 2

    errors = validate_query_plan(payload)
    if errors:
        print_fail_summary(input_path, errors)
        return 2

    print_pass_summary(input_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
