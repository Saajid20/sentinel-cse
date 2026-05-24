from __future__ import annotations

import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.normalization import (  # noqa: E402
    is_shareholder_or_takeover_disclosure,
    normalize_catalyst_tag,
    normalize_catalyst_tags,
    suggest_conservative_policy_for_disclosure,
)


def test_normalize_catalyst_tag_strips_uppercases_and_replaces_separators() -> None:
    assert normalize_catalyst_tag("  local business/update  ") == "LOCAL_BUSINESS_UPDATE"


def test_monetary_policy_aliases_normalize_to_monetary_policy() -> None:
    assert normalize_catalyst_tag("rate cut") == "MONETARY_POLICY"
    assert normalize_catalyst_tag("CBSL-rate-decision") == "MONETARY_POLICY"


def test_pmi_aliases_normalize_to_pmi() -> None:
    assert normalize_catalyst_tag("Purchasing Managers Index") == "PMI"
    assert normalize_catalyst_tag("services/pmi") == "PMI"


def test_fx_aliases_normalize_to_fx_pressure() -> None:
    assert normalize_catalyst_tag("rupee depreciation") == "FX_PRESSURE"
    assert normalize_catalyst_tag("exchange-rate") == "FX_PRESSURE"


def test_earnings_and_accounting_aliases_normalize_correctly() -> None:
    assert normalize_catalyst_tag("strong earnings") == "EARNINGS"
    assert normalize_catalyst_tag("balance sheet") == "ACCOUNTING_FINANCIALS"


def test_disclosure_aliases_normalize_to_corporate_disclosure() -> None:
    assert normalize_catalyst_tag("disclosure") == "CORPORATE_DISCLOSURE"
    assert normalize_catalyst_tag("corporate action") == "CORPORATE_DISCLOSURE"


def test_shareholder_and_takeover_aliases_normalize_to_shareholder_activity() -> None:
    assert normalize_catalyst_tag("takeover disclosure") == "SHAREHOLDER_ACTIVITY"
    assert normalize_catalyst_tag("rule 36") == "SHAREHOLDER_ACTIVITY"


def test_shareholder_stake_aliases_normalize_to_shareholder_activity() -> None:
    aliases = [
        "INSIDER_BUYING",
        "INSIDER_ACQUISITION",
        "SUBSTANTIAL_SHAREHOLDER",
        "SUBSTANTIAL_HOLDING",
        "STAKE_INCREASE",
        "STAKE_ACQUISITION",
        "STAKE_PURCHASE",
        "SHARE_ACQUISITION",
    ]

    for alias in aliases:
        assert normalize_catalyst_tag(alias) == "SHAREHOLDER_ACTIVITY"


def test_normalize_catalyst_tags_deduplicates_while_preserving_order() -> None:
    assert normalize_catalyst_tags(
        ["results", "cash dividend", "results", "earnings"]
    ) == ["EARNINGS", "DIVIDEND"]


def test_normalize_catalyst_tags_collapses_shareholder_aliases_to_one_tag() -> None:
    assert normalize_catalyst_tags(["INSIDER_BUYING", "SHAREHOLDER_CHANGE"]) == [
        "SHAREHOLDER_ACTIVITY"
    ]


def test_normalize_catalyst_tags_drops_unknown_when_known_tags_exist() -> None:
    assert normalize_catalyst_tags([" ", "unknown", "pmi"]) == ["PMI"]


def test_normalize_catalyst_tags_returns_unknown_for_empty_or_all_unknown_input() -> None:
    assert normalize_catalyst_tags([]) == ["UNKNOWN"]
    assert normalize_catalyst_tags([" ", "unknown"]) == ["UNKNOWN"]


def test_is_shareholder_or_takeover_disclosure_detects_tag_aliases() -> None:
    assert is_shareholder_or_takeover_disclosure(["takeovers code"]) is True


def test_is_shareholder_or_takeover_disclosure_detects_rule_36_stake_and_shareholder_text() -> None:
    assert (
        is_shareholder_or_takeover_disclosure(
            ["corporate disclosure"],
            short_summary="Disclosure under Rule 36 after a shareholder stake change.",
        )
        is True
    )


def test_suggest_conservative_policy_for_disclosure_downgrades_support() -> None:
    assert (
        suggest_conservative_policy_for_disclosure(
            ["corporate disclosure"],
            "SUPPORT",
            short_summary="Substantial holding update under the Takeovers Code.",
        )
        == "MANUAL_REVIEW"
    )


def test_suggest_conservative_policy_for_disclosure_leaves_other_policies_unchanged() -> None:
    assert (
        suggest_conservative_policy_for_disclosure(
            ["shareholder activity"],
            "BLOCK",
        )
        == "BLOCK"
    )
    assert (
        suggest_conservative_policy_for_disclosure(
            ["shareholder activity"],
            "MANUAL_REVIEW",
        )
        == "MANUAL_REVIEW"
    )
    assert (
        suggest_conservative_policy_for_disclosure(
            ["shareholder activity"],
            "NO_EFFECT",
        )
        == "NO_EFFECT"
    )
