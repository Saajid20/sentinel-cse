from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.context_bridge import CandidateContextRequest  # noqa: E402


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
            "best_median_spread_percent": 0.30,
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


def test_valid_candidate_context_request_payload_passes() -> None:
    payload = make_valid_payload()

    result = CandidateContextRequest.model_validate(payload)

    assert result.schema_version == "candidate-context-request/v0.1"
    assert result.request_id is None
    assert result.ticker == "PKME.N0000"


def test_invalid_schema_version_fails() -> None:
    with pytest.raises(ValidationError, match="candidate-context-request/v0.1"):
        CandidateContextRequest.model_validate(
            make_valid_payload(schema_version="candidate-context-request/v0.2")
        )


def test_non_null_request_id_fails() -> None:
    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(
            make_valid_payload(request_id="req-123")
        )


def test_invalid_review_status_fails() -> None:
    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(
            make_valid_payload(review_status="APPROVED")
        )


def test_invalid_evidence_tier_fails() -> None:
    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(
            make_valid_payload(evidence_tier="Tier Z")
        )


def test_invalid_requested_reviews_value_fails() -> None:
    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(
            make_valid_payload(
                requested_reviews=["R10_CONTEXT_RISK", "LIVE_EXECUTION"]
            )
        )


def test_false_safety_flag_fails() -> None:
    payload = make_valid_payload()
    payload["safety"]["human_review_required"] = False

    with pytest.raises(ValidationError, match="human_review_required must be true"):
        CandidateContextRequest.model_validate(payload)


def test_unsafe_trading_action_language_in_warnings_fails() -> None:
    with pytest.raises(ValidationError, match="warnings contains unsafe trading recommendation language"):
        CandidateContextRequest.model_validate(
            make_valid_payload(warnings=["Buy now after review"])
        )


def test_negative_counts_fail() -> None:
    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(
            make_valid_payload(diagnostic_count=-1)
        )


def test_null_metric_rollups_pass() -> None:
    payload = make_valid_payload(
        technical_summary={
            "total_filtered_count": 0,
            "first_session": None,
            "last_session": None,
            "best_median_spread_percent": None,
            "best_bid_ask_coverage_ratio": None,
            "max_latest_turnover": None,
        }
    )

    result = CandidateContextRequest.model_validate(payload)

    assert result.technical_summary.best_median_spread_percent is None
    assert result.technical_summary.best_bid_ask_coverage_ratio is None
    assert result.technical_summary.max_latest_turnover is None


def test_extra_unknown_fields_fail() -> None:
    payload = make_valid_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        CandidateContextRequest.model_validate(payload)


def test_empty_session_stems_item_fails() -> None:
    payload = make_valid_payload()
    payload["artifact_refs"]["session_stems"] = ["good-session", " "]

    with pytest.raises(ValidationError, match="session_stems item must not be empty"):
        CandidateContextRequest.model_validate(payload)
