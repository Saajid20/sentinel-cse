from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.extraction.pypdf_row_parser import ParsedFinancialRow
from sentinel_research.agents.r11.schemas import (
    FinancialStatementType,
    MetricUnit,
    NormalizedFinancialLineItem,
    R11ConfidenceLevel,
    SourceTrace,
)

_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": " ",
        "\u2011": " ",
        "\u2012": " ",
        "\u2013": " ",
        "\u2014": " ",
        "\u2212": " ",
    }
)
_LEADING_PREFIX_PATTERN = re.compile(
    r"^(?:less\s*:|less:|add/\(less\):|add\s*/\s*\(less\):)\s*",
    re.IGNORECASE,
)
_MONTH_NAMES = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
_KNOWN_SHORT_FINANCIAL_LABELS = {
    "earnings per share",
    "basic earnings per ordinary share rs",
    "diluted earnings per ordinary share rs",
    "net assets value per ordinary share rs",
    "non controlling interest",
}
_FINANCIAL_KEYWORDS = (
    "income",
    "expense",
    "profit",
    "loss",
    "asset",
    "liabil",
    "equity",
    "interest",
    "deposit",
    "loan",
    "advance",
    "earning",
    "reserve",
    "capital",
    "tax",
    "commission",
    "amortisation",
    "amortization",
    "impairment",
    "share",
)


class NormalizedLineItemMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    original_label: str
    statement_type: FinancialStatementType
    unit: MetricUnit = MetricUnit.UNKNOWN
    confidence: R11ConfidenceLevel = R11ConfidenceLevel.MEDIUM
    matched_alias: str | None = None
    notes: str | None = None

    @field_validator("canonical_name")
    @classmethod
    def _normalize_canonical_name(cls, value: str) -> str:
        normalized = snake_case_name(value)
        if not normalized:
            raise ValueError("canonical_name must not be empty")
        return normalized

    @field_validator("original_label")
    @classmethod
    def _validate_original_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("original_label must not be empty")
        return normalized

    @field_validator("matched_alias", "notes")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


def normalize_label_text(label: str) -> str:
    normalized = label.strip().translate(_DASH_TRANSLATION).lower()
    normalized = _LEADING_PREFIX_PATTERN.sub("", normalized)
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[\"'.,()]+", " ", normalized)
    normalized = re.sub(r"[:;/]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def snake_case_name(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def is_probable_noise_row(row: ParsedFinancialRow) -> bool:
    normalized_label = normalize_label_text(row.label)
    if not normalized_label:
        return True
    if normalized_label in _MONTH_NAMES:
        return True
    if normalized_label.startswith("i certify"):
        return True
    if "companies act no" in normalized_label:
        return True
    if "chairman" in normalized_label or "chief executive officer" in normalized_label:
        return True
    if normalized_label in {
        "number of employees",
        "number of customer service centers",
    }:
        return True
    if re.fullmatch(r"(?:\d{1,2}\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?", normalized_label):
        return True

    if len(row.values) < 3:
        if normalized_label in _KNOWN_SHORT_FINANCIAL_LABELS:
            return False
        if any(keyword in normalized_label for keyword in _FINANCIAL_KEYWORDS):
            return False
        return True

    return False


_ALIAS_MAP: dict[str, str] = {
    "gross income": "gross_income",
    "interest income": "interest_income",
    "interest expense": "interest_expense",
    "net interest income": "net_interest_income",
    "fee and commission income": "fee_and_commission_income",
    "fee and commission expense": "fee_and_commission_expense",
    "net fee and commission income": "net_fee_and_commission_income",
    "total operating income": "total_operating_income",
    "impairment charges and other losses": "impairment_charges_and_other_losses",
    "net operating income": "net_operating_income",
    "expenses": "operating_expenses",
    "personnel expenses": "personnel_expenses",
    "depreciation and amortisation": "depreciation_and_amortisation",
    "other operating expenses": "other_operating_expenses",
    "operating profit before taxes on financial services": "operating_profit_before_taxes_on_financial_services",
    "taxes on financial services": "taxes_on_financial_services",
    "operating profit after taxes on financial services": "operating_profit_after_taxes_on_financial_services",
    "profit before income tax": "profit_before_income_tax",
    "income tax expense": "income_tax_expense",
    "profit for the period": "profit_for_the_period",
    "equity holders of the bank": "profit_attributable_to_equity_holders",
    "non controlling interest": "non_controlling_interest",
    "basic earnings per ordinary share rs": "basic_eps",
    "diluted earnings per ordinary share rs": "diluted_eps",
    "cash and cash equivalents": "cash_and_cash_equivalents",
    "balances with central banks": "balances_with_central_banks",
    "placements with banks": "placements_with_banks",
    "financial assets at amortised cost loans and advances to other customers": "loans_and_advances_to_customers",
    "financial liabilities at amortised cost due to depositors": "customer_deposits",
    "total assets": "total_assets",
    "total liabilities": "total_liabilities",
    "stated capital": "stated_capital",
    "statutory reserves": "statutory_reserves",
    "retained earnings": "retained_earnings",
    "other reserves": "other_reserves",
    "total equity attributable to equity holders of the bank": "total_equity_attributable_to_equity_holders",
    "total equity": "total_equity",
    "total liabilities and equity": "total_liabilities_and_equity",
    "net assets value per ordinary share rs": "net_asset_value_per_share",
}


def infer_metric_unit(canonical_name: str, original_label: str) -> MetricUnit:
    normalized_label = normalize_label_text(original_label)
    normalized_name = snake_case_name(canonical_name)
    if normalized_name.endswith("_eps"):
        return MetricUnit.LKR
    if "per share" in normalized_label or "per ordinary share" in normalized_label:
        return MetricUnit.LKR
    return MetricUnit.UNKNOWN


def map_line_item_label(
    label: str,
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN,
) -> NormalizedLineItemMapping | None:
    original_label = label.strip()
    normalized_label = normalize_label_text(original_label)
    if not normalized_label:
        return None

    alias_match = _ALIAS_MAP.get(normalized_label)
    if alias_match is not None:
        return NormalizedLineItemMapping(
            canonical_name=alias_match,
            original_label=original_label,
            statement_type=statement_type,
            unit=infer_metric_unit(alias_match, original_label),
            confidence=R11ConfidenceLevel.HIGH,
            matched_alias=normalized_label,
        )

    canonical_name = snake_case_name(normalized_label)
    if not canonical_name:
        return None

    return NormalizedLineItemMapping(
        canonical_name=canonical_name,
        original_label=original_label,
        statement_type=statement_type,
        unit=infer_metric_unit(canonical_name, original_label),
        confidence=R11ConfidenceLevel.LOW,
    )


def normalize_parsed_financial_row(
    row: ParsedFinancialRow,
) -> NormalizedFinancialLineItem | None:
    if is_probable_noise_row(row):
        return None

    mapping = map_line_item_label(row.label, row.statement_type)
    if mapping is None:
        return None

    period_values = {
        f"value_{index}": value for index, value in enumerate(row.values, start=1)
    }
    source_trace = _build_source_trace(row)

    return NormalizedFinancialLineItem(
        canonical_name=mapping.canonical_name,
        original_label=row.label,
        statement_type=row.statement_type,
        period_values=period_values,
        unit=mapping.unit,
        source_trace=source_trace,
        normalization_confidence=mapping.confidence,
    )


def normalize_parsed_financial_rows(
    rows: list[ParsedFinancialRow],
) -> list[NormalizedFinancialLineItem]:
    normalized_items: list[NormalizedFinancialLineItem] = []
    for row in rows:
        normalized = normalize_parsed_financial_row(row)
        if normalized is None:
            continue
        normalized_items.append(normalized)
    return normalized_items


def _build_source_trace(row: ParsedFinancialRow) -> SourceTrace | None:
    if row.source_trace is not None:
        return row.source_trace.model_copy(update={"row_label": row.label})

    return SourceTrace(
        page_number=row.page_number,
        table_id=row.table_id,
        row_label=row.label,
        raw_value=row.raw_text,
        notes="line item mapper",
    )
