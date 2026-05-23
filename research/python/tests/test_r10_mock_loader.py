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
    required_expected_keys = {
        "analysis_scope",
        "macro_risk_level",
        "sentiment",
        "signal_policy",
        "must_include_catalyst_tags",
        "must_include_affected_sectors",
        "manual_review_required",
    }

    cases = load_mock_documents()

    for case in cases:
        assert required_case_keys.issubset(case)
        assert required_expected_keys.issubset(case["expected"])


def test_mock_documents_do_not_include_recommendation_language() -> None:
    cases = load_mock_documents()

    for case in cases:
        assert _UNSAFE_PATTERN.search(case["document"]) is None
