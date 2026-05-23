from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from eval_r10_mock_documents import _compare_case  # noqa: E402


def make_analysis(**overrides):
    values = {
        "analysis_scope": "SECTOR",
        "macro_risk_level": "MEDIUM",
        "sentiment": "BULLISH",
        "signal_policy": "SUPPORT",
        "manual_review_required": False,
        "catalyst_tags": ["TOURISM"],
        "affected_sectors": ["LEISURE"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compare_case_tolerant_sector_alias_only_does_not_raise_key_error() -> None:
    case = {
        "expected": {
            "analysis_scope_any_of": ["SECTOR"],
            "macro_risk_level_any_of": ["MEDIUM"],
            "sentiment_any_of": ["BULLISH"],
            "signal_policy_any_of": ["SUPPORT", "MANUAL_REVIEW"],
            "manual_review_required_any_of": [False, True],
            "catalyst_tag_any_of_groups": [["TOURISM", "SECTOR_GROWTH"]],
            "affected_sector_any_of_groups": [["TOURISM", "LEISURE", "HOTELS"]],
        }
    }

    failures = _compare_case(case, make_analysis())

    assert failures == []


def test_compare_case_old_must_include_affected_sectors_fallback_still_works() -> None:
    case = {
        "expected": {
            "analysis_scope": "SECTOR",
            "macro_risk_level": "MEDIUM",
            "sentiment": "BULLISH",
            "signal_policy": "SUPPORT",
            "manual_review_required": False,
            "must_include_catalyst_tags": ["TOURISM"],
            "must_include_affected_sectors": ["LEISURE"],
        }
    }

    failures = _compare_case(case, make_analysis())

    assert failures == []
