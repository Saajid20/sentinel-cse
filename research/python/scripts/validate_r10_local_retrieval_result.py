from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA_VERSION = "r10-local-retrieval-dry-run/v0.1"
REQUIRED_SAFETY_FLAGS = (
    "local_retrieval_only",
    "no_context_agent",
    "no_llm",
    "no_network",
    "no_new_ingestion",
    "no_policy_output",
    "technical_evidence_is_not_source_evidence",
    "human_review_required",
)
_UNSAFE_PATTERN = re.compile(r"\b(?:buy|sell|hold|entry|exit|trade)\b", re.IGNORECASE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an existing R10 local retrieval dry-run JSON file. "
            "This is validation-only and does not rerun retrieval, R10, or network calls."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an existing R10 local retrieval dry-run JSON file.",
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
    if not isinstance(value, list):
        errors.append(f"{field_name}: must be a list")
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


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_retrieval_result(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f'schema_version: must be "{SCHEMA_VERSION}"')

    _non_empty_str(payload.get("query_plan_path"), "query_plan_path", errors)
    _non_empty_str(payload.get("document_store_path"), "document_store_path", errors)

    query_plan_summary = payload.get("query_plan_summary")
    if not isinstance(query_plan_summary, dict):
        errors.append("query_plan_summary: must be an object")
    else:
        _non_empty_str(query_plan_summary.get("ticker"), "query_plan_summary.ticker", errors)
        _string_list(
            query_plan_summary.get("requested_source_labels"),
            "query_plan_summary.requested_source_labels",
            errors,
        )
        _string_list(
            query_plan_summary.get("query_terms"),
            "query_plan_summary.query_terms",
            errors,
        )

    document_query = payload.get("document_query")
    if not isinstance(document_query, dict):
        errors.append("document_query: must be an object")
    else:
        _string_list(document_query.get("tickers"), "document_query.tickers", errors)
        _string_list(document_query.get("keywords"), "document_query.keywords", errors)
        _string_list(document_query.get("source_types"), "document_query.source_types", errors)
        limit = document_query.get("limit")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            errors.append("document_query.limit: must be a positive integer")

    matched_documents = payload.get("matched_documents")
    if not isinstance(matched_documents, list):
        errors.append("matched_documents: must be a list")
        matched_documents_list: list[object] = []
    else:
        matched_documents_list = matched_documents

    matched_document_count = payload.get("matched_document_count")
    if not isinstance(matched_document_count, int) or isinstance(matched_document_count, bool):
        errors.append("matched_document_count: must be an integer")
    elif matched_document_count != len(matched_documents_list):
        errors.append("matched_document_count: must equal len(matched_documents)")

    for index, item in enumerate(matched_documents_list):
        field_prefix = f"matched_documents.{index}"
        if not isinstance(item, dict):
            errors.append(f"{field_prefix}: must be an object")
            continue
        _non_empty_str(item.get("document_id"), f"{field_prefix}.document_id", errors)
        _non_empty_str(item.get("source_type"), f"{field_prefix}.source_type", errors)
        _non_empty_str(item.get("title"), f"{field_prefix}.title", errors)
        reference = item.get("reference")
        if reference is not None and not isinstance(reference, str):
            errors.append(f"{field_prefix}.reference: must be a string or null")
        score = item.get("score")
        if not _is_number(score):
            errors.append(f"{field_prefix}.score: must be numeric")
        _string_list(item.get("matched_reasons"), f"{field_prefix}.matched_reasons", errors)
        _string_list(item.get("tickers_hint"), f"{field_prefix}.tickers_hint", errors)

    warnings = payload.get("warnings")
    normalized_warnings = _string_list(warnings, "warnings", errors)
    for warning in normalized_warnings:
        _check_unsafe_language(warning, "warnings", errors)

    safety = payload.get("safety")
    if not isinstance(safety, dict):
        errors.append("safety: must be an object")
    else:
        for field_name in REQUIRED_SAFETY_FLAGS:
            if safety.get(field_name) is not True:
                errors.append(f"safety.{field_name}: must be true")

    return errors


def print_pass_summary(path: Path, payload: dict[str, object]) -> None:
    query_plan_summary = payload.get("query_plan_summary", {})
    ticker = query_plan_summary.get("ticker") if isinstance(query_plan_summary, dict) else None
    matched_document_count = payload.get("matched_document_count")

    print("R10 local retrieval result validation: PASS")
    print(f"input: {path}")
    print(f"ticker: {ticker}")
    print(f"schema_version: {payload.get('schema_version')}")
    print(f"matched_documents: {matched_document_count}")
    print(f"document_store_path: {payload.get('document_store_path')}")
    print("safety: verified")


def print_fail_summary(path: Path, reasons: list[str]) -> None:
    print("R10 local retrieval result validation: FAIL")
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

    errors = validate_retrieval_result(payload)
    if errors:
        print_fail_summary(input_path, errors)
        return 2

    print_pass_summary(input_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
