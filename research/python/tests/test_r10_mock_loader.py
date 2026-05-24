from __future__ import annotations

import re
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.evals.mock_loader import load_mock_documents  # noqa: E402


FIXTURE_PATH = (
    PYTHON_ROOT
    / "sentinel_research"
    / "agents"
    / "evals"
    / "mock_documents"
    / "r10_mock_documents.jsonl"
)

_UNSAFE_PATTERN = re.compile(r"\b(?:buy|sell|hold|order)\b", re.IGNORECASE)
_FORBIDDEN_EXPECTED_VALUES = {"BUY", "SELL", "HOLD", "LONG", "SHORT", "ORDER", "TARGET_PRICE"}


def test_mock_documents_fixture_exists() -> None:
    assert FIXTURE_PATH.exists()


def test_loader_returns_at_least_ten_cases() -> None:
    cases = load_mock_documents()

    assert len(cases) >= 10


def test_each_case_has_required_fields() -> None:
    required_case_keys = {
        "id",
        "title",
        "source_type",
        "url",
        "published_at",
        "document",
        "expected",
    }

    cases = load_mock_documents()

    for case in cases:
        assert required_case_keys.issubset(case)
        assert isinstance(case["expected"], dict)


def test_each_expected_block_has_exact_or_tolerant_keys() -> None:
    cases = load_mock_documents()

    for case in cases:
        expected = case["expected"]
        assert "analysis_scope" in expected or "analysis_scope_any_of" in expected
        assert "macro_risk_level" in expected or "macro_risk_level_any_of" in expected
        assert "sentiment" in expected or "sentiment_any_of" in expected
        assert "signal_policy" in expected or "signal_policy_any_of" in expected
        assert "manual_review_required" in expected or "manual_review_required_any_of" in expected
        assert (
            "must_include_catalyst_tags" in expected
            or "catalyst_tag_any_of_groups" in expected
        )


def test_tolerant_expectation_fields_are_non_empty_when_present() -> None:
    cases = load_mock_documents()

    for case in cases:
        expected = case["expected"]
        for key in (
            "analysis_scope_any_of",
            "macro_risk_level_any_of",
            "sentiment_any_of",
            "signal_policy_any_of",
            "manual_review_required_any_of",
        ):
            if key in expected:
                assert isinstance(expected[key], list)
                assert expected[key]

        for key in ("catalyst_tag_any_of_groups", "affected_sector_any_of_groups"):
            if key in expected:
                assert isinstance(expected[key], list)
                for group in expected[key]:
                    assert isinstance(group, list)
                    assert group


def _walk_expected_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_expected_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_expected_strings(item)


def test_mock_documents_do_not_include_recommendation_language() -> None:
    cases = load_mock_documents()

    for case in cases:
        assert _UNSAFE_PATTERN.search(case["document"]) is None


def test_expected_values_do_not_include_forbidden_trading_terms() -> None:
    cases = load_mock_documents()

    for case in cases:
        for value in _walk_expected_strings(case["expected"]):
            assert value.upper() not in _FORBIDDEN_EXPECTED_VALUES
