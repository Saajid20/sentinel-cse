from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PYTHON_ROOT / "scripts"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from dry_run_r10_candidate_retrieval import (  # noqa: E402
    build_document_query_from_payload,
    build_parser,
    main,
    map_query_plan_source_types,
)
from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument  # noqa: E402
from sentinel_research.agents.schemas import SourceType  # noqa: E402


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-local-retrieval-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


def make_query_plan_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "r10-candidate-query-plan/v0.1",
        "candidate_request_path": ".runtime-pipeline/candidate-context-requests/PKME.N0000.json",
        "ticker": "PKME.N0000",
        "company_name": "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
        "evidence_tier": "Tier A",
        "review_status": "MANUAL_REVIEW",
        "requested_reviews": [
            "R10_CONTEXT_RISK",
            "R11_FINANCIAL_STATEMENT",
            "CSE_DISCLOSURE",
            "HUMAN_NOTES",
        ],
        "requested_source_types": [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
        ],
        "query_terms": [
            "PKME.N0000",
            "PKME",
            "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
            "DIGITAL MOBILITY SOLUTIONS LANKA",
        ],
        "cbsl_context": {
            "included": False,
            "reason": "CBSL macro context is deferred unless an explicit macro-relevance rule exists.",
        },
        "required_validations": [
            "validate_candidate_context_request",
            "source_integrity_check",
            "R10_schema_validation",
            "policy_consistency_guard",
            "unsafe_trading_language_guard",
            "human_review_required",
        ],
        "artifact_refs": {
            "runtime_root": ".runtime-pipeline/multi-session-validation",
            "session_stems": [
                "atrad-session-20260602-040121",
                "atrad-session-20260602-042010",
            ],
            "dossier_markdown_path": ".runtime-pipeline/candidate-dossiers/PKME.N0000.md",
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
    payload.update(overrides)
    return payload


def make_document(**overrides: object) -> SourceDocument:
    payload = {
        "document_id": "doc-001",
        "source_type": "CSE_DISCLOSURE",
        "title": "PKME issuer update",
        "url": "https://example.com/pkme-disclosure",
        "published_at": "2026-06-02T10:00:00Z",
        "retrieved_at": "2026-06-02T11:00:00Z",
        "raw_text": "PKME.N0000 DIGITAL MOBILITY SOLUTIONS LANKA PLC issuer update.",
        "normalized_text": "PKME.N0000 DIGITAL MOBILITY SOLUTIONS LANKA PLC issuer update.",
        "tickers_hint": ["PKME.N0000"],
        "sectors_hint": [],
        "metadata": {"file_path": "C:/docs/pkme-update.pdf"},
    }
    payload.update(overrides)
    return SourceDocument.model_validate(payload)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_cli(query_plan_path: Path, document_store_path: Path) -> tuple[int, str]:
    return run_cli_with_optional_json(query_plan_path, document_store_path, None)


def run_cli_with_optional_json(
    query_plan_path: Path,
    document_store_path: Path,
    json_output_path: Path | None,
) -> tuple[int, str]:
    buffer = io.StringIO()
    argv = [
        "--query-plan",
        str(query_plan_path),
        "--document-store",
        str(document_store_path),
    ]
    if json_output_path is not None:
        argv.extend(["--json-output", str(json_output_path)])
    with redirect_stdout(buffer):
        exit_code = main(argv)
    return exit_code, buffer.getvalue()


def test_cli_parses_json_output_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--query-plan",
            "query-plan.json",
            "--document-store",
            "documents.jsonl",
            "--json-output",
            "output.json",
        ]
    )

    assert args.json_output == "output.json"


def test_valid_query_plan_builds_deterministic_document_query() -> None:
    payload = make_query_plan_payload()

    first = build_document_query_from_payload(payload)
    second = build_document_query_from_payload(payload)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.tickers == ["PKME.N0000"]
    assert first.limit == 10


def test_default_cse_source_labels_map_to_cse_disclosure() -> None:
    mapped = map_query_plan_source_types(
        ["CSE_DISCLOSURE", "CSE_ANNOUNCEMENT", "CSE_FINANCIAL_DISCLOSURE"]
    )

    assert mapped == [SourceType.CSE_DISCLOSURE]


def test_cbsl_context_excluded_by_default() -> None:
    payload = make_query_plan_payload()

    query = build_document_query_from_payload(payload)

    assert query.source_types == [SourceType.CSE_DISCLOSURE]


def test_explicit_cbsl_context_maps_to_cbsl() -> None:
    payload = make_query_plan_payload(
        requested_source_types=[
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
            "CBSL_CONTEXT",
        ],
        cbsl_context={
            "included": True,
            "reason": "Explicit macro relevance exists for this review path.",
        },
    )

    query = build_document_query_from_payload(payload)

    assert query.source_types == [SourceType.CSE_DISCLOSURE, SourceType.CBSL]


def test_ticker_and_company_query_terms_map_correctly() -> None:
    payload = make_query_plan_payload()

    query = build_document_query_from_payload(payload)

    assert query.tickers == ["PKME.N0000"]
    assert query.keywords == [
        "PKME",
        "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
        "DIGITAL MOBILITY SOLUTIONS LANKA",
    ]


def test_dry_run_prints_matched_local_documents(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append_many(
        [
            make_document(document_id="doc-newer", retrieved_at="2026-06-02T12:00:00Z"),
            make_document(document_id="doc-older", retrieved_at="2026-06-02T11:00:00Z"),
        ]
    )

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert "R10 local retrieval dry-run" in output
    assert "matched document count: 2" in output
    assert "document_id: doc-newer" in output
    assert "source_type: CSE_DISCLOSURE" in output
    assert "matched_reasons:" in output
    assert output.index("document_id: doc-newer") < output.index("document_id: doc-older")


def test_empty_local_store_handled_clearly(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    store_path.write_text("", encoding="utf-8")

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert "matched document count: 0" in output
    assert "empty local store: no SourceDocument records found" in output


def test_no_matches_handled_clearly(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(
        make_document(
            document_id="doc-other",
            tickers_hint=["OTHER.N0000"],
            raw_text="Unrelated issuer update.",
            normalized_text="Unrelated issuer update.",
            title="Other issuer update",
        )
    )

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert "matched document count: 0" in output
    assert "no local documents matched the mapped retrieval query" in output


def test_invalid_query_plan_fails_cleanly(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    invalid_payload = make_query_plan_payload(schema_version="bad-version")
    write_json(query_plan_path, invalid_payload)
    LocalDocumentStore(store_path).append(make_document())

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 2
    assert "R10 local retrieval dry-run: FAIL" in output
    assert "schema_version" in output
    assert "Traceback" not in output


def test_invalid_document_store_fails_cleanly(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    store_path.write_text("{not-json}\n", encoding="utf-8")

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 2
    assert "invalid document store" in output
    assert "Traceback" not in output


def test_no_context_agent_network_or_ingestion_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network call should not happen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert "matched document count: 1" in output


def test_no_files_written(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    exit_code, _ = run_cli(query_plan_path, store_path)
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    assert exit_code == 0
    assert before == after


def test_no_json_file_written_unless_json_output_passed(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "out" / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert not json_output_path.exists()


def test_json_output_parent_directory_created_automatically(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "nested" / "retrieval" / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)

    assert exit_code == 0
    assert json_output_path.exists()


def test_json_output_contains_expected_top_level_fields(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["schema_version"] == "r10-local-retrieval-dry-run/v0.1"
    assert payload["query_plan_path"] == str(query_plan_path)
    assert payload["document_store_path"] == str(store_path)
    assert set(payload) == {
        "schema_version",
        "query_plan_path",
        "document_store_path",
        "query_plan_summary",
        "document_query",
        "matched_document_count",
        "matched_documents",
        "warnings",
        "safety",
    }


def test_json_output_includes_query_plan_summary(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["query_plan_summary"] == {
        "ticker": "PKME.N0000",
        "company_name": "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
        "requested_source_labels": [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
        ],
        "query_terms": [
            "PKME.N0000",
            "PKME",
            "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
            "DIGITAL MOBILITY SOLUTIONS LANKA",
        ],
    }


def test_json_output_includes_document_query_summary(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["document_query"] == {
        "tickers": ["PKME.N0000"],
        "keywords": [
            "PKME",
            "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
            "DIGITAL MOBILITY SOLUTIONS LANKA",
        ],
        "source_types": ["CSE_DISCLOSURE"],
        "limit": 10,
    }


def test_json_output_includes_matched_local_documents_with_confirmed_fields(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["matched_document_count"] == 1
    assert payload["matched_documents"] == [
        {
            "document_id": "doc-001",
            "source_type": "CSE_DISCLOSURE",
            "title": "PKME issuer update",
            "reference": "C:/docs/pkme-update.pdf",
            "score": 5.25,
            "matched_reasons": [
                "keyword:PKME",
                "keyword:DIGITAL MOBILITY SOLUTIONS LANKA PLC",
                "keyword:DIGITAL MOBILITY SOLUTIONS LANKA",
                "ticker:PKME.N0000",
                "source_type:CSE_DISCLOSURE",
            ],
            "tickers_hint": ["PKME.N0000"],
        }
    ]


def test_empty_local_store_exports_zero_matches_with_warning(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    store_path.write_text("", encoding="utf-8")

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["matched_document_count"] == 0
    assert payload["matched_documents"] == []
    assert payload["warnings"] == ["empty local store: no SourceDocument records found"]


def test_no_matches_exports_zero_matches_with_warning(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(
        make_document(
            document_id="doc-other",
            tickers_hint=["OTHER.N0000"],
            raw_text="Unrelated issuer update.",
            normalized_text="Unrelated issuer update.",
            title="Other issuer update",
        )
    )

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload = json.loads(json_output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["matched_document_count"] == 0
    assert payload["matched_documents"] == []
    assert payload["warnings"] == ["no local documents matched the mapped retrieval query"]


def test_invalid_query_plan_does_not_write_json(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload(schema_version="bad-version"))
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)

    assert exit_code == 2
    assert not json_output_path.exists()


def test_invalid_document_store_does_not_write_json(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    store_path.write_text("{not-json}\n", encoding="utf-8")

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)

    assert exit_code == 2
    assert not json_output_path.exists()


def test_terminal_output_still_prints_when_json_export_used(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, output = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)

    assert exit_code == 0
    assert "R10 local retrieval dry-run" in output
    assert "matched document count: 1" in output
    assert json_output_path.exists()


def test_generated_json_contains_no_trading_action_language_tokens(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    json_output_path = tmp_path / "result.json"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, _ = run_cli_with_optional_json(query_plan_path, store_path, json_output_path)
    payload_text = json_output_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert re.search(r"\b(?:BUY|SELL|HOLD|ENTRY|EXIT|TRADE)\b", payload_text) is None


def test_no_trading_action_language_in_output(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append(make_document())

    exit_code, output = run_cli(query_plan_path, store_path)

    assert exit_code == 0
    assert re.search(r"\b(?:BUY|SELL|HOLD|ENTRY|EXIT|TRADE)\b", output) is None


def test_deterministic_output_ordering(tmp_path: Path) -> None:
    query_plan_path = tmp_path / "query-plan.json"
    store_path = tmp_path / "documents.jsonl"
    write_json(query_plan_path, make_query_plan_payload())
    LocalDocumentStore(store_path).append_many(
        [
            make_document(document_id="doc-a", retrieved_at="2026-06-02T11:00:00Z"),
            make_document(document_id="doc-b", retrieved_at="2026-06-02T12:00:00Z"),
        ]
    )

    first_exit, first_output = run_cli(query_plan_path, store_path)
    second_exit, second_output = run_cli(query_plan_path, store_path)

    assert first_exit == 0
    assert second_exit == 0
    assert first_output == second_output
