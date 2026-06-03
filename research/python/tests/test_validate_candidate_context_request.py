from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_candidate_context_request import main  # noqa: E402


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
        "company_name": "Digital Mobility Solutions Lanka PLC",
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


def test_valid_request_file_returns_success_and_prints_pass(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 0
        assert "CandidateContextRequest validation: PASS" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_schema_version_returns_failure_and_prints_fail(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        write_json(
            request_path,
            make_valid_payload(schema_version="candidate-context-request/v0.2"),
        )

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "CandidateContextRequest validation: FAIL" in captured
        assert "schema_version" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_invalid_requested_reviews_returns_failure(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        write_json(
            request_path,
            make_valid_payload(
                requested_reviews=["R10_CONTEXT_RISK", "LIVE_EXECUTION"]
            ),
        )

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "requested_reviews" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_false_safety_flag_returns_failure(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        payload = make_valid_payload()
        payload["safety"]["human_review_required"] = False
        write_json(request_path, payload)

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "safety.human_review_required" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_unsafe_trading_action_language_in_warnings_returns_failure(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        write_json(request_path, make_valid_payload(warnings=["buy after review"]))

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "warnings" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_malformed_json_returns_failure_with_clear_message(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "bad.json"
        request_path.write_text("{not-json", encoding="utf-8")

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "CandidateContextRequest validation: FAIL" in captured
        assert "malformed JSON" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_missing_file_returns_failure_with_clear_message(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "missing.json"

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "missing file" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_valid_output_summary_includes_required_fields(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 0
        assert "ticker: PKME.N0000" in captured
        assert "schema_version: candidate-context-request/v0.1" in captured
        assert "review_status: MANUAL_REVIEW" in captured
        assert "evidence_tier: Tier A" in captured
        assert (
            "requested_reviews: R10_CONTEXT_RISK, R11_FINANCIAL_STATEMENT, "
            "CSE_DISCLOSURE, HUMAN_NOTES" in captured
        )
        assert "safety: verified" in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_cli_does_not_write_any_output_files(capsys) -> None:
    directory = make_temp_dir()
    try:
        request_path = directory / "PKME.N0000.json"
        write_json(request_path, make_valid_payload())
        before = sorted(path.relative_to(directory) for path in directory.rglob("*"))

        exit_code = main(["--input", str(request_path)])

        after = sorted(path.relative_to(directory) for path in directory.rglob("*"))
        assert exit_code == 0
        assert before == after
        assert "PASS" in capsys.readouterr().out
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_schema_error_output_is_compact_and_has_no_traceback(capsys) -> None:
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

        exit_code = main(["--input", str(request_path)])

        captured = capsys.readouterr().out
        assert exit_code == 2
        assert "Traceback" not in captured
        assert "ValidationError" not in captured
    finally:
        shutil.rmtree(directory, ignore_errors=True)
