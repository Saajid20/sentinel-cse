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

from build_r10_candidate_context_request import main  # noqa: E402
from build_r10_candidate_context_request import build_parser  # noqa: E402


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def make_valid_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "schema_version": "candidate-context-request/v0.1",
        "request_id": None,
        "ticker": "PKME.N0000",
        "company_name": "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
        "generated_from_dossier": True,
        "evidence_tier": "Tier A",
        "review_status": "MANUAL_REVIEW",
        "sessions_seen": 2,
        "strong_full_grid_sessions": 1,
        "partial_coverage_sessions": 1,
        "baseline_count": 1,
        "diagnostic_count": 5,
        "variants_seen": ["base", "vol-off", "imb-off", "both-off"],
        "technical_summary": {
            "total_filtered_count": 6,
            "first_session": "atrad-session-20260602-040121",
            "last_session": "atrad-session-20260602-042010",
            "best_median_spread_percent": 0.3,
            "best_bid_ask_coverage_ratio": 1.0,
            "max_latest_turnover": 5324618.5,
        },
        "warnings": [],
        "requested_reviews": [
            "R10_CONTEXT_RISK",
            "R11_FINANCIAL_STATEMENT",
            "CSE_DISCLOSURE",
            "HUMAN_NOTES",
        ],
        "artifact_refs": {
            "runtime_root": ".runtime-pipeline/multi-session-validation",
            "dossier_markdown_path": ".runtime-pipeline/candidate-dossiers/PKME.N0000.md",
            "session_stems": [
                "atrad-session-20260602-040121",
                "atrad-session-20260602-042010",
            ],
        },
        "safety": {
            "research_only": True,
            "not_financial_advice": True,
            "not_buy_sell_hold_recommendation": True,
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


def test_cli_parses_json_output_flag() -> None:
    args = build_parser().parse_args(
        ["--input", "request.json", "--json-output", "out/plan.json"]
    )

    assert args.input == "request.json"
    assert args.json_output == "out/plan.json"


def test_valid_request_prints_dry_run_summary_and_returns_zero() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        assert "R10 candidate context dry-run query plan" in output
        assert "Validated candidate request summary" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_candidate_request_json_fails_cleanly_and_returns_non_zero() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        write_json(
            request_path,
            make_valid_payload(schema_version="candidate-context-request/v0.2"),
        )

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 2
        assert "FAIL" in output
        assert "schema_version" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_file_fails_cleanly() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "missing.json"

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 2
        assert "missing file" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_query_terms_include_ticker_root_company_and_simplified_company() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        assert "- PKME.N0000" in output
        assert "- PKME" in output
        assert "- DIGITAL MOBILITY SOLUTIONS LANKA PLC" in output
        assert "- DIGITAL MOBILITY SOLUTIONS LANKA" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_requested_source_types_include_default_cse_types() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        assert "- CSE_DISCLOSURE" in output
        assert "- CSE_ANNOUNCEMENT" in output
        assert "- CSE_FINANCIAL_DISCLOSURE" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cbsl_context_is_not_included_by_default() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        assert "- CBSL_CONTEXT" not in output
        assert "CBSL macro context is deferred unless an explicit macro-relevance rule exists." in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_includes_required_validations() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        for item in (
            "validate_candidate_context_request",
            "source_integrity_check",
            "R10_schema_validation",
            "policy_consistency_guard",
            "unsafe_trading_language_guard",
            "human_review_required",
        ):
            assert f"- {item}" in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_contains_no_uppercase_trading_action_language_tokens() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        for token in ("BUY", "SELL", "HOLD", "ENTRY", "EXIT", "TRADE"):
            assert token not in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_script_writes_no_files() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())
        before = sorted(path.relative_to(directory) for path in directory.rglob("*"))

        exit_code, _output = run_cli(["--input", str(request_path)])

        after = sorted(path.relative_to(directory) for path in directory.rglob("*"))
        assert exit_code == 0
        assert before == after
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_no_json_file_is_written_without_flag() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        expected_json_path = directory / "plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(["--input", str(request_path)])

        assert exit_code == 0
        assert not expected_json_path.exists()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_parent_directory_is_created_automatically_for_json_output() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "nested" / "plans" / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        assert exit_code == 0
        assert json_path.is_file()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_json_output_contains_expected_top_level_fields() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload["schema_version"] == "r10-candidate-query-plan/v0.1"
        assert payload["candidate_request_path"] == str(request_path)
        assert payload["ticker"] == "PKME.N0000"
        assert payload["company_name"] == "DIGITAL MOBILITY SOLUTIONS LANKA PLC"
        assert payload["evidence_tier"] == "Tier A"
        assert payload["review_status"] == "MANUAL_REVIEW"
        assert payload["requested_reviews"] == [
            "R10_CONTEXT_RISK",
            "R11_FINANCIAL_STATEMENT",
            "CSE_DISCLOSURE",
            "HUMAN_NOTES",
        ]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_json_output_contains_requested_source_types() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload["requested_source_types"] == [
            "CSE_DISCLOSURE",
            "CSE_ANNOUNCEMENT",
            "CSE_FINANCIAL_DISCLOSURE",
        ]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_json_output_does_not_include_cbsl_context_by_default() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert "CBSL_CONTEXT" not in payload["requested_source_types"]
        assert payload["cbsl_context"] == {
            "included": False,
            "reason": "CBSL macro context is deferred unless an explicit macro-relevance rule exists.",
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_json_output_contains_expected_query_terms() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload["query_terms"] == [
            "PKME.N0000",
            "PKME",
            "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
            "DIGITAL MOBILITY SOLUTIONS LANKA",
        ]
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_json_safety_object_is_present() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload["safety"] == {
            "retrieval_intent_only": True,
            "no_r10_execution": True,
            "no_network": True,
            "technical_evidence_is_not_source_evidence": True,
            "not_financial_advice": True,
            "not_live_execution_guidance": True,
            "human_review_required": True,
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_terminal_output_remains_present_when_json_export_is_used() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        assert exit_code == 0
        assert "Validated candidate request summary" in output
        assert json_path.is_file()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_input_does_not_write_json() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        json_path = directory / "bad.plan.json"
        write_json(
            request_path,
            make_valid_payload(schema_version="candidate-context-request/v0.2"),
        )

        exit_code, output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        assert exit_code == 2
        assert "FAIL" in output
        assert not json_path.exists()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_generated_json_contains_no_uppercase_trading_action_tokens() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        json_path = directory / "PKME.N0000.plan.json"
        write_json(request_path, make_valid_payload())

        exit_code, _output = run_cli(
            ["--input", str(request_path), "--json-output", str(json_path)]
        )

        dumped = json_path.read_text(encoding="utf-8")
        assert exit_code == 0
        for token in ("BUY", "SELL", "HOLD", "ENTRY", "EXIT", "TRADE"):
            assert token not in dumped
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_output_is_deterministic_for_same_input() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        first_exit_code, first_output = run_cli(["--input", str(request_path)])
        second_exit_code, second_output = run_cli(["--input", str(request_path)])

        assert first_exit_code == 0
        assert second_exit_code == 0
        assert first_output == second_output
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_validation_failure_output_is_compact_and_has_no_traceback_text() -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        write_json(
            request_path,
            make_valid_payload(
                schema_version="candidate-context-request/v0.2",
                requested_reviews=["LIVE_EXECUTION"],
            ),
        )

        exit_code, output = run_cli(["--input", str(request_path)])

        assert exit_code == 2
        assert "Traceback" not in output
        assert "ValidationError" not in output
    finally:
        shutil.rmtree(directory, ignore_errors=True)
