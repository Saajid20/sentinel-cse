from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.policy import (  # noqa: E402
    R10DecisionPolicy,
    R10PolicyDecision,
    StrategyCandidateType,
    TechnicalSignalCandidate,
    evaluate_r10_policy,
)
from sentinel_research.agents.reports import R10AnalysisReport  # noqa: E402


def make_candidate(**overrides: object) -> TechnicalSignalCandidate:
    payload = {
        "candidate_id": "candidate-001",
        "ticker": " jkh.n0000 ",
        "strategy_candidate_type": "MOMENTUM_BREAKOUT_READY",
        "detected_at": "2026-05-24T12:00:00Z",
        "metadata": {},
    }
    payload.update(overrides)
    return TechnicalSignalCandidate.model_validate(payload)


def make_analysis_payload(**overrides: object) -> dict[str, object]:
    payload = {
        "schema_version": "r10_news_analyst_v1",
        "analysis_scope": "TICKER",
        "ticker": "JKH.N0000",
        "sector": None,
        "macro_risk_level": "MEDIUM",
        "sentiment": "NEUTRAL",
        "catalyst_tags": ["corporate disclosure"],
        "affected_tickers": ["JKH.N0000"],
        "affected_sectors": [],
        "signal_policy": "SUPPORT",
        "manual_review_required": False,
        "confidence": 0.65,
        "valid_until": "2026-05-25T00:00:00Z",
        "staleness_risk": "LOW",
        "reason_codes": ["INFO_ONLY"],
        "short_summary": "Validated context remains neutral and informational.",
        "sources": [
            {
                "source_type": "CSE_DISCLOSURE",
                "title": "Corporate disclosure",
                "url": "https://cdn.cse.lk/cmt/doc.pdf",
                "published_at": "2026-05-23T10:00:00Z",
                "retrieved_at": "2026-05-23T10:30:00Z",
            }
        ],
    }
    payload.update(overrides)
    return payload


def make_report(**overrides: object) -> R10AnalysisReport:
    payload = {
        "report_id": "r10_ticker_context_20260524T120000Z_JKH.N0000",
        "report_type": "TICKER_CONTEXT",
        "generated_at": "2026-05-24T12:00:00Z",
        "query": {"tickers": ["JKH.N0000"], "limit": 1},
        "analysis": make_analysis_payload(),
        "source_document_ids": ["doc-001"],
        "notes": " offline report ",
    }
    payload.update(overrides)
    return R10AnalysisReport.model_validate(payload)


def test_technical_signal_candidate_validates_and_uppercased_ticker() -> None:
    candidate = make_candidate()

    assert candidate.ticker == "JKH.N0000"
    assert candidate.strategy_candidate_type is StrategyCandidateType.MOMENTUM_BREAKOUT_READY


def test_technical_signal_candidate_rejects_empty_candidate_id_and_ticker() -> None:
    with pytest.raises(ValidationError, match="candidate_id must not be empty"):
        make_candidate(candidate_id="   ")

    with pytest.raises(ValidationError, match="ticker must not be empty"):
        make_candidate(ticker="   ")


def test_r10_policy_decision_schema_version_is_locked() -> None:
    with pytest.raises(ValidationError, match="r10_policy_decision_v1"):
        R10PolicyDecision(
            schema_version="r10_policy_decision_v2",
            candidate_id="candidate-001",
            ticker="JKH.N0000",
            strategy_candidate_type=StrategyCandidateType.UNKNOWN,
            r10_report_id="report-001",
            r10_policy=R10DecisionPolicy.NO_EFFECT,
            manual_review_required=False,
            reason_codes=["R10_POLICY_NO_EFFECT"],
            source_report_type="TICKER_CONTEXT",
            source_analysis_scope="TICKER",
            source_macro_risk_level="LOW",
            source_sentiment="NEUTRAL",
            normalized_catalyst_tags=["UNKNOWN"],
            generated_at=datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC),
        )


def test_evaluate_r10_policy_returns_support_when_no_conservative_rule_applies() -> None:
    candidate = make_candidate()
    report = make_report(analysis=make_analysis_payload(catalyst_tags=["earnings"]))

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.SUPPORT
    assert decision.manual_review_required is False


def test_high_macro_risk_forces_block() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            macro_risk_level="HIGH",
            catalyst_tags=["earnings"],
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.BLOCK
    assert "R10_HIGH_MACRO_RISK_BLOCK" in decision.reason_codes


def test_report_signal_policy_block_remains_block() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            signal_policy="BLOCK",
            catalyst_tags=["earnings"],
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.BLOCK
    assert "R10_ANALYSIS_BLOCK" in decision.reason_codes


def test_manual_review_required_true_forces_manual_review_unless_block() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            manual_review_required=True,
            catalyst_tags=["earnings"],
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.MANUAL_REVIEW
    assert "R10_ANALYSIS_MANUAL_REVIEW_REQUIRED" in decision.reason_codes


def test_shareholder_takeover_disclosure_downgrades_support_to_manual_review() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            catalyst_tags=["takeover disclosure"],
            short_summary="Disclosure under Rule 36 of the Takeovers Code.",
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.MANUAL_REVIEW
    assert "R10_SHAREHOLDER_ACTIVITY_REVIEW" in decision.reason_codes


def test_ticker_mismatch_forces_manual_review_unless_block() -> None:
    candidate = make_candidate(ticker="COMB.N0000")
    report = make_report(analysis=make_analysis_payload(catalyst_tags=["earnings"]))

    decision = evaluate_r10_policy(candidate, report)

    assert decision.r10_policy is R10DecisionPolicy.MANUAL_REVIEW
    assert "R10_TICKER_MISMATCH_REVIEW" in decision.reason_codes


def test_reason_codes_include_deterministic_and_prefixed_analysis_reason_codes() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            manual_review_required=True,
            catalyst_tags=["earnings"],
            reason_codes=["INFO_ONLY", "INFO_ONLY", " CSE_DISCLOSURE "],
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.reason_codes[:3] == [
        "R10_ANALYSIS_MANUAL_REVIEW_REQUIRED",
        "ANALYSIS_INFO_ONLY",
        "ANALYSIS_CSE_DISCLOSURE",
    ]


def test_normalized_catalyst_tags_are_included_and_deduped() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            catalyst_tags=[" results ", "earnings", "unknown", "cash dividend"],
        )
    )

    decision = evaluate_r10_policy(candidate, report)

    assert decision.normalized_catalyst_tags == ["EARNINGS", "DIVIDEND"]


def test_manual_review_required_output_is_true_for_block_and_manual_review() -> None:
    candidate = make_candidate()
    block_report = make_report(
        analysis=make_analysis_payload(
            signal_policy="BLOCK",
            catalyst_tags=["earnings"],
        )
    )
    review_report = make_report(
        analysis=make_analysis_payload(
            manual_review_required=True,
            catalyst_tags=["earnings"],
        )
    )

    block_decision = evaluate_r10_policy(candidate, block_report)
    review_decision = evaluate_r10_policy(candidate, review_report)

    assert block_decision.manual_review_required is True
    assert review_decision.manual_review_required is True


def test_evaluate_r10_policy_does_not_mutate_report_catalyst_tags() -> None:
    candidate = make_candidate()
    report = make_report(
        analysis=make_analysis_payload(
            catalyst_tags=[" results ", "cash dividend"],
        )
    )
    original_tags = list(report.analysis.catalyst_tags)

    evaluate_r10_policy(candidate, report)

    assert report.analysis.catalyst_tags == original_tags
