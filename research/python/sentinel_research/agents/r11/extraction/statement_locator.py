from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sentinel_research.agents.r11.schemas import (
    ExtractedFinancialTable,
    FinancialStatementType,
    R11ConfidenceLevel,
)


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
    has_assets = "ASSETS" in normalized_text
    has_liabilities = "LIABILITIES" in normalized_text
    has_total_assets = "TOTAL ASSETS" in normalized_text
    has_total_liabilities = "TOTAL LIABILITIES" in normalized_text
    has_balance_sheet_structure = has_assets and has_liabilities
    has_strong_balance_sheet_markers = has_financial_position_title or (
        has_balance_sheet_structure and (has_total_assets or has_total_liabilities)
    )

    if has_profit_or_loss_statement_title:
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
    elif "STATEMENT OF CHANGES IN EQUITY" in normalized_text:
        statement_type = FinancialStatementType.EQUITY_STATEMENT
        confidence = R11ConfidenceLevel.HIGH
        matched_markers.append("STATEMENT OF CHANGES IN EQUITY")
    elif "CASH FLOWS" in normalized_text or "CASH FLOW" in normalized_text:
        statement_type = FinancialStatementType.CASH_FLOW
        if "CASH FLOWS" in normalized_text:
            matched_markers.append("CASH FLOWS")
        if "CASH FLOW" in normalized_text and "CASH FLOWS" not in normalized_text:
            matched_markers.append("CASH FLOW")
        if "OPERATING ACTIVITIES" in normalized_text:
            matched_markers.append("OPERATING ACTIVITIES")
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


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped
