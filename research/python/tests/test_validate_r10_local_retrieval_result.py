from __future__ import annotations

import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from uuid import uuid4

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_r10_local_retrieval_result import main  # noqa: E402


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def make_valid_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "schema_version": "r10-local-retrieval-dry-run/v0.1",
        "query_plan_path": ".runtime-pipeline/r10-candidate-query-plans/PKME.N0000.json",
        "document_store_path": "research/python/.r10_runtime/cse_announcements/cse_announcement_documents.jsonl",
        "query_plan_summary": {
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
        },
        "document_query": {
            "tickers": ["PKME.N0000"],
            "keywords": [
                "PKME",
                "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
                "DIGITAL MOBILITY SOLUTIONS LANKA",
            ],
            "source_types": ["CSE_DISCLOSURE"],
            "limit": 10,
        },
        "matched_document_count": 1,
        "matched_documents": [
            {
                "document_id": "doc-001",
                "source_type": "CSE_DISCLOSURE",
                "title": "PKME issuer update",
                "reference": "C:/docs/pkme-update.pdf",
                "score": 5.25,
                "matched_reasons": [
                    "keyword:PKME",
                    "ticker:PKME.N0000",
                    "source_type:CSE_DISCLOSURE",
                ],
                "tickers_hint": ["PKME.N0000"],
            }
        ],
        "warnings": [],
        "safety": {
            "local_retrieval_only": True,
            "no_context_agent": True,
            "no_llm": True,
            "no_network": True,
            "no_new_ingestion": True,
            "no_policy_output": True,
            "technical_evidence_is_not_source_evidence": True,
            "human_review_required": True,
        },
    }
    payload.update(overrides)
    return payload


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_cli(args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


def test_valid_retrieval_result_file_returns_pass() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "PKME.N0000.json"
        write_json(result_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 0
        assert "R10 local retrieval result validation: PASS" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_schema_version_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        write_json(result_path, make_valid_payload(schema_version="bad"))

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "schema_version" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_matched_document_count_mismatch_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        write_json(result_path, make_valid_payload(matched_document_count=2))

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "matched_document_count" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_false_safety_flag_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["safety"]["no_network"] = False
        write_json(result_path, payload)

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "safety.no_network" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_matched_document_field_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        payload = make_valid_payload()
        del payload["matched_documents"][0]["title"]
        write_json(result_path, payload)

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "matched_documents.0.title" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_score_type_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["matched_documents"][0]["score"] = "high"
        write_json(result_path, payload)

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "matched_documents.0.score" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_malformed_json_fails_clearly() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        result_path.write_text("{not-json", encoding="utf-8")

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "malformed JSON" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_file_fails_clearly() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "missing.json"

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "missing file" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_warning_containing_trading_action_language_fails() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        write_json(result_path, make_valid_payload(warnings=["buy after retrieval review"]))

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "warnings" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_summary_includes_required_fields() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "PKME.N0000.json"
        write_json(result_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 0
        assert "ticker: PKME.N0000" in output
        assert "schema_version: r10-local-retrieval-dry-run/v0.1" in output
        assert "matched_documents: 1" in output
        assert "document_store_path: research/python/.r10_runtime/cse_announcements/cse_announcement_documents.jsonl" in output
        assert "safety: verified" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_traceback_text_on_normal_failures() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "bad.json"
        write_json(result_path, make_valid_payload(schema_version="bad"))

        exit_code, output = run_cli(["--input", str(result_path)])

        assert exit_code == 2
        assert "Traceback" not in output
        assert "ValidationError" not in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cli_writes_no_files() -> None:
    directory = make_temp_dir()
    try:
        result_path = directory / "PKME.N0000.json"
        write_json(result_path, make_valid_payload())
        before = sorted(path.relative_to(directory) for path in directory.rglob("*"))

        exit_code, _output = run_cli(["--input", str(result_path)])

        after = sorted(path.relative_to(directory) for path in directory.rglob("*"))
        assert exit_code == 0
        assert before == after
    finally:
        shutil.rmtree(directory, ignore_errors=True)
