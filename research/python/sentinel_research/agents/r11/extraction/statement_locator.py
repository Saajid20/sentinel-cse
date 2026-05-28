from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sentinel_research.agents.r11.schemas import (
    ExtractedFinancialTable,
    FinancialStatementType,
    R11ConfidenceLevel,
)

_CASH_FLOW_TITLE_MARKERS = [
    "STATEMENT OF CASH FLOWS",
    "STATEMENT OF CASH FLOW",
]

_CASH_FLOW_STRUCTURE_MARKERS = [
    "CASH FLOWS FROM OPERATING ACTIVITIES",
    "OPERATING ACTIVITIES",
    "INTEREST RECEIPTS",
    "INTEREST PAYMENTS",
    "OPERATING PROFIT BEFORE CHANGES IN OPERATING ASSETS & LIABILITIES",
    "OPERATING PROFIT BEFORE CHANGES IN OPERATING ASSETS AND LIABILITIES",
    "NET CASH GENERATED FROM / USED IN OPERATING ACTIVITIES",
    "NET CASH GENERATED FROM USED IN OPERATING ACTIVITIES",
]

_EQUITY_TITLE_MARKERS = [
    "STATEMENT OF CHANGES IN EQUITY",
]

_EQUITY_STRUCTURE_MARKERS = [
    "BALANCE AS AT 1ST JANUARY",
    "BALANCE AS AT 31ST MARCH",
    "BALANCE AS AT 31 MARCH",
    "BALANCE AS AT 31ST DECEMBER",
    "BALANCE AS AT 31 DECEMBER",
    "TRANSACTIONS WITH EQUITY HOLDERS",
    "CONTRIBUTIONS BY AND DISTRIBUTIONS TO EQUITY HOLDERS",
    "FINAL DIVIDEND",
    "UNCLAIMED DIVIDEND ADJUSTMENTS",
    "TRANSFER TO RESERVES",
    "STATED CAPITAL",
    "STATUTORY RESERVE FUND",
    "RETAINED EARNINGS",
]

_INCOME_STATEMENT_TITLE_MARKERS = [
    "STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME",
    "INCOME STATEMENT",
    "STATEMENT OF COMPREHENSIVE INCOME",
]

_INCOME_STATEMENT_ROW_MARKERS = [
    "GROSS INCOME",
    "INTEREST INCOME",
    "INTEREST EXPENSE",
    "NET INTEREST INCOME",
    "FEE & COMMISSION INCOME",
    "FEE AND COMMISSION INCOME",
    "TOTAL OPERATING INCOME",
    "IMPAIRMENT CHARGE/(REVERSAL)",
    "IMPAIRMENT CHARGE",
    "TOTAL OPERATING EXPENSES",
    "PROFIT BEFORE INCOME TAX",
    "PROFIT FOR THE PERIOD",
]

_COMPREHENSIVE_INCOME_MARKERS = [
    "OTHER COMPREHENSIVE INCOME",
    "TOTAL COMPREHENSIVE INCOME FOR THE PERIOD NET OF TAX",
    "TOTAL COMPREHENSIVE INCOME FOR THE PERIOD",
    "STATEMENT OF COMPREHENSIVE INCOME",
]


class StatementPageMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    table_id: str
    statement_type: FinancialStatementType
    confidence: R11ConfidenceLevel
    matched_markers: list[str]
    notes: str | None = None

    @field_validator("page_number")
    @classmethod
    def _validate_page_number(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("page_number must be positive")
        return value

    @field_validator("table_id")
    @classmethod
    def _validate_table_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("table_id must not be empty")
        return normalized

    @field_validator("matched_markers")
    @classmethod
    def _normalize_markers(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for marker in value:
            stripped = marker.strip()
            if stripped:
                normalized.append(stripped)
        return normalized

    @field_validator("notes")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @model_validator(mode="after")
    def _validate_marker_requirement(self) -> StatementPageMatch:
        if self.statement_type is not FinancialStatementType.UNKNOWN and not self.matched_markers:
            raise ValueError("matched_markers must not be empty unless statement_type is UNKNOWN")
        return self


def page_text_from_extracted_table(table: ExtractedFinancialTable) -> str:
    lines: list[str] = []
    for row in table.rows:
        text = row.get("text")
        if text is None:
            continue
        normalized = str(text).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def classify_statement_page(table: ExtractedFinancialTable) -> StatementPageMatch:
    page_text = page_text_from_extracted_table(table)
    normalized_text = page_text.upper()
    matched_markers: list[str] = []
    statement_type = FinancialStatementType.UNKNOWN
    confidence = R11ConfidenceLevel.LOW
    notes: str | None = None

    has_income_statement_title = "INCOME STATEMENT" in normalized_text
    has_profit_or_loss_statement_title = (
        "STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME" in normalized_text
    )
    has_financial_position_title = "STATEMENT OF FINANCIAL POSITION" in normalized_text
    has_equity_title = "STATEMENT OF CHANGES IN EQUITY" in normalized_text
    has_assets = "ASSETS" in normalized_text
    has_liabilities = "LIABILITIES" in normalized_text
    has_total_assets = "TOTAL ASSETS" in normalized_text
    has_total_liabilities = "TOTAL LIABILITIES" in normalized_text
    has_balance_sheet_structure = has_assets and has_liabilities
    has_strong_balance_sheet_markers = has_financial_position_title or (
        has_balance_sheet_structure and (has_total_assets or has_total_liabilities)
    )
    cash_flow_title_markers = _find_present_markers(normalized_text, _CASH_FLOW_TITLE_MARKERS)
    cash_flow_structure_markers = _find_present_markers(normalized_text, _CASH_FLOW_STRUCTURE_MARKERS)
    equity_title_markers = _find_present_markers(normalized_text, _EQUITY_TITLE_MARKERS)
    equity_structure_markers = _find_present_markers(normalized_text, _EQUITY_STRUCTURE_MARKERS)
    income_title_markers = _find_present_markers(normalized_text, _INCOME_STATEMENT_TITLE_MARKERS)
    income_row_markers = _find_present_markers(normalized_text, _INCOME_STATEMENT_ROW_MARKERS)
    comprehensive_income_markers = _find_present_markers(normalized_text, _COMPREHENSIVE_INCOME_MARKERS)

    if cash_flow_title_markers or _has_strong_cash_flow_structure(cash_flow_structure_markers):
        statement_type = FinancialStatementType.CASH_FLOW
        matched_markers.extend(cash_flow_title_markers)
        matched_markers.extend(cash_flow_structure_markers)
        if cash_flow_title_markers or "NET CASH GENERATED FROM / USED IN OPERATING ACTIVITIES" in cash_flow_structure_markers:
            confidence = R11ConfidenceLevel.HIGH
        elif len(cash_flow_structure_markers) >= 3:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
    elif has_equity_title or _has_strong_equity_structure(equity_structure_markers):
        statement_type = FinancialStatementType.EQUITY_STATEMENT
        matched_markers.extend(equity_title_markers)
        matched_markers.extend(equity_structure_markers)
        if has_equity_title or len(equity_structure_markers) >= 4:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
    elif has_profit_or_loss_statement_title:
        statement_type = FinancialStatementType.INCOME_STATEMENT
        confidence = R11ConfidenceLevel.HIGH
        matched_markers.append("STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME")
    elif has_income_statement_title:
        statement_type = FinancialStatementType.INCOME_STATEMENT
        matched_markers.append("INCOME STATEMENT")
        if "GROSS INCOME" in normalized_text or "PROFIT FOR THE PERIOD" in normalized_text:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
        if "GROSS INCOME" in normalized_text:
            matched_markers.append("GROSS INCOME")
        if "PROFIT FOR THE PERIOD" in normalized_text:
            matched_markers.append("PROFIT FOR THE PERIOD")
    elif "STATEMENT OF COMPREHENSIVE INCOME" in normalized_text:
        statement_type = FinancialStatementType.INCOME_STATEMENT
        matched_markers.extend(income_title_markers)
        matched_markers.extend(comprehensive_income_markers)
        if len(comprehensive_income_markers) >= 2:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
    elif _has_strong_income_statement_structure(
        income_row_markers=income_row_markers,
        comprehensive_income_markers=comprehensive_income_markers,
    ):
        statement_type = FinancialStatementType.INCOME_STATEMENT
        matched_markers.extend(income_row_markers)
        matched_markers.extend(comprehensive_income_markers)
        if len(income_row_markers) >= 4 or len(comprehensive_income_markers) >= 2:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
    elif has_strong_balance_sheet_markers or has_balance_sheet_structure:
        statement_type = FinancialStatementType.BALANCE_SHEET
        if has_financial_position_title:
            matched_markers.append("STATEMENT OF FINANCIAL POSITION")
        if has_assets:
            matched_markers.append("ASSETS")
        if has_liabilities:
            matched_markers.append("LIABILITIES")
        if has_total_assets:
            matched_markers.append("TOTAL ASSETS")
        if has_total_liabilities:
            matched_markers.append("TOTAL LIABILITIES")
        if has_strong_balance_sheet_markers:
            confidence = R11ConfidenceLevel.HIGH
        else:
            confidence = R11ConfidenceLevel.MEDIUM
    elif "NOTES TO THE FINANCIAL STATEMENTS" in normalized_text:
        statement_type = FinancialStatementType.NOTES
        confidence = R11ConfidenceLevel.MEDIUM
        matched_markers.append("NOTES TO THE FINANCIAL STATEMENTS")
    else:
        first_line = normalized_text.splitlines()[0] if normalized_text.splitlines() else ""
        if first_line.startswith("NOTE ") or first_line.startswith("NOTES "):
            statement_type = FinancialStatementType.NOTES
            confidence = R11ConfidenceLevel.MEDIUM
            matched_markers.append(first_line)
            notes = "Classified from note-style page heading."

    return StatementPageMatch(
        page_number=table.page_number or 0,
        table_id=table.table_id,
        statement_type=statement_type,
        confidence=confidence,
        matched_markers=_dedupe_preserving_order(matched_markers),
        notes=notes,
    )


def locate_statement_pages(tables: list[ExtractedFinancialTable]) -> list[StatementPageMatch]:
    return [classify_statement_page(table) for table in tables]


def _find_present_markers(normalized_text: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker in normalized_text]


def _has_strong_cash_flow_structure(markers: list[str]) -> bool:
    return len(markers) >= 2


def _has_strong_equity_structure(markers: list[str]) -> bool:
    if len(markers) >= 3:
        return True
    has_balance_marker = any(marker.startswith("BALANCE AS AT ") for marker in markers)
    has_equity_column_marker = any(
        marker in {"STATED CAPITAL", "STATUTORY RESERVE FUND", "RETAINED EARNINGS"}
        for marker in markers
    )
    return has_balance_marker and has_equity_column_marker


def _has_strong_income_statement_structure(
    *,
    income_row_markers: list[str],
    comprehensive_income_markers: list[str],
) -> bool:
    return len(income_row_markers) >= 3 or len(comprehensive_income_markers) >= 2


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped
