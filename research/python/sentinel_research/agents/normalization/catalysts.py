from __future__ import annotations

import re

MONETARY_POLICY = "MONETARY_POLICY"
PMI = "PMI"
FX_PRESSURE = "FX_PRESSURE"
INFLATION = "INFLATION"
FUEL_ENERGY_SHOCK = "FUEL_ENERGY_SHOCK"
TAX_POLICY = "TAX_POLICY"
EARNINGS = "EARNINGS"
DIVIDEND = "DIVIDEND"
CORPORATE_DISCLOSURE = "CORPORATE_DISCLOSURE"
SHAREHOLDER_ACTIVITY = "SHAREHOLDER_ACTIVITY"
RIGHTS_ISSUE = "RIGHTS_ISSUE"
BOARD_CHANGE = "BOARD_CHANGE"
MERGER_ACQUISITION = "MERGER_ACQUISITION"
ACCOUNTING_FINANCIALS = "ACCOUNTING_FINANCIALS"
TOURISM_RECOVERY = "TOURISM_RECOVERY"
LOCAL_BUSINESS_UPDATE = "LOCAL_BUSINESS_UPDATE"
UNKNOWN = "UNKNOWN"

_SEPARATOR_PATTERN = re.compile(r"[\s\-/]+")
_UNDERSCORE_PATTERN = re.compile(r"_+")
_TEXT_SIGNAL_PATTERN = re.compile(
    r"\b(?:takeover|takeovers\s+code|rule\s*36|shareholder|stake|substantial\s+holding)\b",
    re.IGNORECASE,
)

_ALIAS_TO_CANONICAL = {
    "RATE_CUT": MONETARY_POLICY,
    "RATE_HIKE": MONETARY_POLICY,
    "POLICY_RATE": MONETARY_POLICY,
    "CBSL_RATE_DECISION": MONETARY_POLICY,
    "INTEREST_RATE": MONETARY_POLICY,
    "MONETARY": MONETARY_POLICY,
    "MONETARY_POLICY": MONETARY_POLICY,
    "PURCHASING_MANAGERS_INDEX": PMI,
    "MANUFACTURING_PMI": PMI,
    "SERVICES_PMI": PMI,
    "PMI": PMI,
    "CURRENCY": FX_PRESSURE,
    "RUPEE": FX_PRESSURE,
    "RUPEE_DEPRECIATION": FX_PRESSURE,
    "EXCHANGE_RATE": FX_PRESSURE,
    "FX_PRESSURE": FX_PRESSURE,
    "INFLATION": INFLATION,
    "ENERGY": FUEL_ENERGY_SHOCK,
    "FUEL": FUEL_ENERGY_SHOCK,
    "OIL_PRICE": FUEL_ENERGY_SHOCK,
    "FUEL_PRICE": FUEL_ENERGY_SHOCK,
    "FUEL_ENERGY_SHOCK": FUEL_ENERGY_SHOCK,
    "TAX": TAX_POLICY,
    "VAT": TAX_POLICY,
    "GOVERNMENT_TAX": TAX_POLICY,
    "TAX_POLICY": TAX_POLICY,
    "RESULTS": EARNINGS,
    "PROFIT": EARNINGS,
    "EARNINGS_IMPROVEMENT": EARNINGS,
    "STRONG_EARNINGS": EARNINGS,
    "EARNINGS": EARNINGS,
    "CASH_DIVIDEND": DIVIDEND,
    "FINAL_DIVIDEND": DIVIDEND,
    "INTERIM_DIVIDEND": DIVIDEND,
    "DIVIDEND": DIVIDEND,
    "DISCLOSURE": CORPORATE_DISCLOSURE,
    "COMPANY_DISCLOSURE": CORPORATE_DISCLOSURE,
    "CORPORATE_ACTION": CORPORATE_DISCLOSURE,
    "CORPORATE_DISCLOSURE": CORPORATE_DISCLOSURE,
    "SHAREHOLDER_CHANGE": SHAREHOLDER_ACTIVITY,
    "SHAREHOLDER_ACTIVITY": SHAREHOLDER_ACTIVITY,
    "TAKEOVER_DISCLOSURE": SHAREHOLDER_ACTIVITY,
    "TAKEOVERS_CODE": SHAREHOLDER_ACTIVITY,
    "RULE_36": SHAREHOLDER_ACTIVITY,
    "INSIDER_BUYING": SHAREHOLDER_ACTIVITY,
    "INSIDER_ACQUISITION": SHAREHOLDER_ACTIVITY,
    "SUBSTANTIAL_SHAREHOLDER": SHAREHOLDER_ACTIVITY,
    "SUBSTANTIAL_HOLDING": SHAREHOLDER_ACTIVITY,
    "STAKE_INCREASE": SHAREHOLDER_ACTIVITY,
    "STAKE_ACQUISITION": SHAREHOLDER_ACTIVITY,
    "STAKE_PURCHASE": SHAREHOLDER_ACTIVITY,
    "SHARE_ACQUISITION": SHAREHOLDER_ACTIVITY,
    "RIGHTS": RIGHTS_ISSUE,
    "RIGHTS_ISSUE": RIGHTS_ISSUE,
    "CAPITAL_RAISING": RIGHTS_ISSUE,
    "DIRECTOR_CHANGE": BOARD_CHANGE,
    "BOARD_APPOINTMENT": BOARD_CHANGE,
    "BOARD_RESIGNATION": BOARD_CHANGE,
    "BOARD_CHANGE": BOARD_CHANGE,
    "MERGER": MERGER_ACQUISITION,
    "ACQUISITION": MERGER_ACQUISITION,
    "M_AND_A": MERGER_ACQUISITION,
    "TAKEOVER": MERGER_ACQUISITION,
    "MERGER_ACQUISITION": MERGER_ACQUISITION,
    "FINANCIAL_STATEMENT": ACCOUNTING_FINANCIALS,
    "BALANCE_SHEET": ACCOUNTING_FINANCIALS,
    "INCOME_STATEMENT": ACCOUNTING_FINANCIALS,
    "ASSET_GROWTH": ACCOUNTING_FINANCIALS,
    "IMPAIRMENT_DROP": ACCOUNTING_FINANCIALS,
    "CAPITAL_RATIOS": ACCOUNTING_FINANCIALS,
    "ACCOUNTING_FINANCIALS": ACCOUNTING_FINANCIALS,
    "TOURISM": TOURISM_RECOVERY,
    "TOURISM_RECOVERY": TOURISM_RECOVERY,
    "ARRIVALS": TOURISM_RECOVERY,
    "EXPANSION": LOCAL_BUSINESS_UPDATE,
    "BUSINESS_UPDATE": LOCAL_BUSINESS_UPDATE,
    "LOCAL_BUSINESS": LOCAL_BUSINESS_UPDATE,
    "LOCAL_BUSINESS_UPDATE": LOCAL_BUSINESS_UPDATE,
    "UNKNOWN": UNKNOWN,
}


def _normalize_raw_tag(tag: str) -> str:
    normalized = _SEPARATOR_PATTERN.sub("_", tag.strip().upper())
    normalized = _UNDERSCORE_PATTERN.sub("_", normalized).strip("_")
    return normalized


def normalize_catalyst_tag(tag: str) -> str:
    normalized = _normalize_raw_tag(tag)
    if not normalized:
        return UNKNOWN
    return _ALIAS_TO_CANONICAL.get(normalized, normalized)


def normalize_catalyst_tags(tags: list[str]) -> list[str]:
    normalized_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = normalize_catalyst_tag(tag)
        if normalized in seen:
            continue
        normalized_tags.append(normalized)
        seen.add(normalized)

    if not normalized_tags or all(tag == UNKNOWN for tag in normalized_tags):
        return [UNKNOWN]

    return [tag for tag in normalized_tags if tag != UNKNOWN]


def is_shareholder_or_takeover_disclosure(
    tags: list[str],
    reason_codes: list[str] | None = None,
    short_summary: str | None = None,
) -> bool:
    normalized_tags = normalize_catalyst_tags(tags)
    if SHAREHOLDER_ACTIVITY in normalized_tags:
        return True

    normalized_reason_codes = normalize_catalyst_tags(reason_codes or [])
    if SHAREHOLDER_ACTIVITY in normalized_reason_codes:
        return True

    text_blocks = [short_summary or ""]
    text_blocks.extend(reason_codes or [])
    combined_text = " ".join(block for block in text_blocks if block.strip())
    return bool(_TEXT_SIGNAL_PATTERN.search(combined_text))


def suggest_conservative_policy_for_disclosure(
    tags: list[str],
    current_policy: str,
    reason_codes: list[str] | None = None,
    short_summary: str | None = None,
) -> str:
    if (
        is_shareholder_or_takeover_disclosure(
            tags,
            reason_codes=reason_codes,
            short_summary=short_summary,
        )
        and current_policy.strip().upper() == "SUPPORT"
    ):
        return "MANUAL_REVIEW"
    return current_policy
