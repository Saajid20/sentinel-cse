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

from validate_r10_candidate_query_plan import main  # noqa: E402


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def make_valid_payload(**overrides: object) -> dict[str, object]:
    payload = {
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


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_cli(args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


def test_valid_query_plan_file_returns_success_and_prints_pass() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "PKME.N0000.json"
        write_json(plan_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 0
        assert "R10 candidate query plan validation: PASS" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_schema_version_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        write_json(plan_path, make_valid_payload(schema_version="r10-candidate-query-plan/v0.2"))

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "schema_version" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_required_source_type_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["requested_source_types"] = [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
        ]
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "missing required source type CSE_FINANCIAL_DISCLOSURE" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_source_type_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["requested_source_types"] = [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
            "LIVE_EXECUTION",
        ]
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "invalid source type LIVE_EXECUTION" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cbsl_context_present_while_included_false_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["requested_source_types"] = [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
            "CBSL_CONTEXT",
        ]
        payload["cbsl_context"] = {
            "included": False,
            "reason": "CBSL macro context is deferred unless an explicit macro-relevance rule exists.",
        }
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "CBSL_CONTEXT must not appear" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_false_safety_flag_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["safety"]["no_network"] = False
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "safety.no_network: must be true" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_required_validation_fails() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["required_validations"] = [
            "validate_candidate_context_request",
            "source_integrity_check",
        ]
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "missing required validation R10_schema_validation" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_empty_query_terms_fail() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["query_terms"] = []
        write_json(plan_path, payload)

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "query_terms" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_malformed_json_fails_clearly() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        plan_path.write_text("{not-json", encoding="utf-8")

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "malformed JSON" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_file_fails_clearly() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "missing.json"

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "missing file" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_summary_includes_required_fields() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "PKME.N0000.json"
        write_json(plan_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 0
        assert "ticker: PKME.N0000" in output
        assert "schema_version: r10-candidate-query-plan/v0.1" in output
        assert (
            "requested_source_types: CSE_DISCLOSURE, CSE_ANNOUNCEMENT, "
            "CSE_FINANCIAL_DISCLOSURE" in output
        )
        assert "query_terms: 4" in output
        assert "cbsl_context: deferred" in output
        assert "safety: verified" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_has_no_traceback_for_normal_validation_errors() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "bad.json"
        write_json(plan_path, make_valid_payload(schema_version="bad"))

        exit_code, output = run_cli(["--input", str(plan_path)])

        assert exit_code == 2
        assert "Traceback" not in output
        assert "ValidationError" not in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cli_writes_no_files() -> None:
    directory = make_temp_dir()
    try:
        plan_path = directory / "PKME.N0000.json"
        write_json(plan_path, make_valid_payload())
        before = sorted(path.relative_to(directory) for path in directory.rglob("*"))

        exit_code, _output = run_cli(["--input", str(plan_path)])

        after = sorted(path.relative_to(directory) for path in directory.rglob("*"))
        assert exit_code == 0
        assert before == after
    finally:
        shutil.rmtree(directory, ignore_errors=True)
