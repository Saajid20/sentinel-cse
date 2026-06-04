from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.retrieval import (  # noqa: E402
    DocumentQuery,
    RetrievalResult,
    SimpleDocumentRetriever,
)
from sentinel_research.agents.schemas import SourceType  # noqa: E402
from validate_r10_candidate_query_plan import (  # noqa: E402
    load_json_payload,
    validate_query_plan,
)

DEFAULT_LIMIT = 10
QUERY_PLAN_TO_SOURCE_TYPE = {
    "CSE_DISCLOSURE": SourceType.CSE_DISCLOSURE,
    "CSE_ANNOUNCEMENT": SourceType.CSE_DISCLOSURE,
    "CSE_FINANCIAL_DISCLOSURE": SourceType.CSE_DISCLOSURE,
    "CBSL_CONTEXT": SourceType.CBSL,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local-only R10 retrieval dry-run from an existing validated "
            "candidate query-plan JSON and an explicit LocalDocumentStore JSONL file."
        )
    )
    parser.add_argument(
        "--query-plan",
        required=True,
        help="Path to an existing r10-candidate-query-plan JSON file.",
    )
    parser.add_argument(
        "--document-store",
        required=True,
        help="Path to an existing LocalDocumentStore JSONL file.",
    )
    return parser


def dedupe_keep_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def map_query_plan_source_types(requested_source_types: list[str]) -> list[SourceType]:
    mapped: list[SourceType] = []
    for label in requested_source_types:
        source_type = QUERY_PLAN_TO_SOURCE_TYPE.get(label)
        if source_type is None:
            continue
        if source_type not in mapped:
            mapped.append(source_type)
    return mapped


def build_document_query_from_payload(payload: dict[str, object]) -> DocumentQuery:
    ticker = str(payload["ticker"]).strip()
    raw_query_terms = payload.get("query_terms", [])
    query_terms = raw_query_terms if isinstance(raw_query_terms, list) else []
    keywords = [
        str(term).strip()
        for term in query_terms
        if isinstance(term, str) and term.strip() and term.strip() != ticker
    ]
    requested_source_types = payload.get("requested_source_types", [])
    source_labels = requested_source_types if isinstance(requested_source_types, list) else []
    mapped_source_types = map_query_plan_source_types(
        [str(item).strip() for item in source_labels if isinstance(item, str)]
    )
    return DocumentQuery(
        tickers=[ticker],
        keywords=keywords,
        sectors=[],
        source_types=mapped_source_types,
        limit=DEFAULT_LIMIT,
    )


def load_documents_from_store(path: Path):
    if not path.exists() or not path.is_file():
        raise ValueError(f"missing file: {path}")

    store = LocalDocumentStore(path)
    try:
        return store.load_all()
    except OSError as error:
        raise ValueError(f"unreadable file: {path} ({error})") from error
    except ValueError as error:
        raise ValueError(f"invalid document store: {error}") from error


def reference_for_result(result: RetrievalResult) -> str:
    document = result.document
    file_path = document.metadata.get("file_path")
    if isinstance(file_path, str) and file_path.strip():
        return file_path.strip()
    if document.url:
        return document.url
    return "unavailable"


def build_warnings(documents_count: int, results: list[RetrievalResult]) -> list[str]:
    warnings: list[str] = []
    if documents_count == 0:
        warnings.append("empty local store: no SourceDocument records found")
    if documents_count > 0 and not results:
        warnings.append("no local documents matched the mapped retrieval query")
    for result in results:
        if reference_for_result(result) == "unavailable":
            warnings.append(
                f"document {result.document.document_id} has no file_path or URL reference"
            )
    return warnings


def render_report(
    query_plan_path: Path,
    document_store_path: Path,
    payload: dict[str, object],
    query: DocumentQuery,
    results: list[RetrievalResult],
    warnings: list[str],
) -> str:
    requested_source_labels = payload.get("requested_source_types", [])
    query_terms = payload.get("query_terms", [])
    source_label_text = (
        ", ".join(str(item) for item in requested_source_labels)
        if isinstance(requested_source_labels, list) and requested_source_labels
        else "none"
    )
    query_terms_text = (
        ", ".join(str(item) for item in query_terms)
        if isinstance(query_terms, list) and query_terms
        else "none"
    )
    mapped_source_types = ", ".join(source_type.value for source_type in query.source_types) or "none"

    lines = [
        "R10 local retrieval dry-run",
        "",
        "Query plan summary",
        f"- query_plan: {query_plan_path}",
        f"- document_store: {document_store_path}",
        f"- ticker: {payload.get('ticker')}",
        f"- company_name: {payload.get('company_name') or 'unavailable'}",
        f"- schema_version: {payload.get('schema_version')}",
        f"- requested source labels: {source_label_text}",
        f"- query terms: {query_terms_text}",
        "",
        "Local DocumentQuery summary",
        f"- tickers: {', '.join(query.tickers) or 'none'}",
        f"- keywords: {', '.join(query.keywords) or 'none'}",
        f"- mapped SourceType values: {mapped_source_types}",
        f"- limit: {query.limit}",
        "",
        "Retrieval results",
        f"- matched document count: {len(results)}",
    ]

    for index, result in enumerate(results, start=1):
        document = result.document
        lines.extend(
            [
                f"- document {index}",
                f"  document_id: {document.document_id}",
                f"  source_type: {document.source_type.value}",
                f"  title: {document.title}",
                f"  reference: {reference_for_result(result)}",
                f"  score: {result.score}",
                "  matched_reasons: "
                + (", ".join(result.matched_reasons) if result.matched_reasons else "unavailable"),
                "  tickers_hint: "
                + (", ".join(document.tickers_hint) if document.tickers_hint else "unavailable"),
            ]
        )

    lines.extend(["", "Warnings"])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "Safety note",
            "- local retrieval only",
            "- no ContextAgent",
            "- no LLM",
            "- no network",
            "- no new ingestion",
            "- no policy output",
            "- technical candidate evidence is not source evidence",
            "- human review required",
        ]
    )
    return "\n".join(lines)


def print_fail_summary(query_plan_path: Path, reasons: list[str]) -> None:
    print("R10 local retrieval dry-run: FAIL")
    print(f"query_plan: {query_plan_path}")
    print("reason:")
    for reason in reasons:
        print(f"* {reason}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query_plan_path = Path(args.query_plan).expanduser()
    document_store_path = Path(args.document_store).expanduser()

    try:
        payload = load_json_payload(query_plan_path)
    except ValueError as error:
        print_fail_summary(query_plan_path, [str(error)])
        return 2

    validation_errors = validate_query_plan(payload)
    if validation_errors:
        print_fail_summary(query_plan_path, validation_errors)
        return 2

    try:
        documents = load_documents_from_store(document_store_path)
    except ValueError as error:
        print_fail_summary(query_plan_path, [str(error)])
        return 2

    query = build_document_query_from_payload(payload)
    results = SimpleDocumentRetriever(documents).search(query)
    warnings = build_warnings(len(documents), results)
    print(render_report(query_plan_path, document_store_path, payload, query, results, warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
