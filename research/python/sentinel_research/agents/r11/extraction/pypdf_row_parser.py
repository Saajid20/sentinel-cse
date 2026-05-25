from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.schemas import (
    ExtractedFinancialTable,
    FinancialStatementType,
    SourceTrace,
)

_VALUE_TOKEN_PATTERN = re.compile(
    r"^(?:\(?\d[\d,]*(?:\.\d+)?\)?|-|Rs\.\d[\d,]*(?:\.\d+)?)$",
    re.IGNORECASE,
)
_DATE_HEADER_PATTERN = re.compile(
    r"\b(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b",
    re.IGNORECASE,
)
_HEADER_PHRASES = (
    "STATEMENT OF",
    "INCOME STATEMENT",
    "PROFIT OR LOSS",
    "FINANCIAL POSITION",
    "AS AT",
)


class ParsedFinancialRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    table_id: str
    line_number: int
    label: str
    raw_text: str
    values: list[str]
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN
    source_trace: SourceTrace | None = None

    @field_validator("page_number", "line_number")
    @classmethod
    def _validate_positive_int(cls, value: int, info) -> int:
        if value <= 0:
            raise ValueError(f"{info.field_name} must be positive")
        return value

    @field_validator("table_id", "label", "raw_text")
    @classmethod
    def _validate_non_empty_text(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("values")
    @classmethod
    def _validate_values(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
        if not normalized:
            raise ValueError("values must not be empty")
        return normalized


def parse_numeric_tokens(text: str) -> list[str]:
    tokens = re.split(r"\s+", text.strip())
    return [token for token in tokens if _VALUE_TOKEN_PATTERN.fullmatch(token)]


def strip_numeric_tokens_from_label(text: str, values: list[str]) -> str:
    if not values:
        return re.sub(r"\s+", " ", text.strip())

    tokens = re.split(r"\s+", text.strip())
    trailing_value_count = 0
    for token in reversed(tokens):
        if _VALUE_TOKEN_PATTERN.fullmatch(token):
            trailing_value_count += 1
            continue
        break

    if trailing_value_count == 0:
        return re.sub(r"\s+", " ", text.strip())

    label_tokens = tokens[:-trailing_value_count]
    return re.sub(r"\s+", " ", " ".join(label_tokens).strip())


def parse_financial_row_text(
    text: str,
    *,
    page_number: int,
    table_id: str,
    line_number: int,
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN,
    source_trace: SourceTrace | None = None,
) -> ParsedFinancialRow | None:
    normalized_text = re.sub(r"\s+", " ", text.strip())
    if not normalized_text:
        return None

    values = parse_numeric_tokens(normalized_text)
    if len(values) < 2:
        return None

    label = strip_numeric_tokens_from_label(normalized_text, values)
    if not label:
        return None

    upper_text = normalized_text.upper()
    upper_label = label.upper()
    if upper_text.isdigit():
        return None
    if upper_label in {"GROUP", "BANK", "GROUP BANK"}:
        return None
    if "RS.'000" in upper_text and len(values) <= 2 and "%" in upper_text:
        return None
    if _DATE_HEADER_PATTERN.search(upper_text) and (
        "FOR THE" in upper_text or "ENDED" in upper_text or "AS AT" in upper_text
    ):
        return None
    if any(phrase in upper_label for phrase in _HEADER_PHRASES):
        return None

    return ParsedFinancialRow(
        page_number=page_number,
        table_id=table_id,
        line_number=line_number,
        label=label,
        raw_text=normalized_text,
        values=values,
        statement_type=statement_type,
        source_trace=source_trace,
    )


def parse_financial_rows_from_table(
    table: ExtractedFinancialTable,
    *,
    statement_type: FinancialStatementType | None = None,
) -> list[ParsedFinancialRow]:
    parsed_rows: list[ParsedFinancialRow] = []
    resolved_statement_type = statement_type or table.statement_type
    page_number = table.page_number or 0

    for row in table.rows:
        line_number = int(row.get("line_number", 0))
        raw_text = str(row.get("text", "")).strip()
        source_trace = SourceTrace(
            local_file_path=table.source_trace.local_file_path if table.source_trace else None,
            page_number=table.page_number,
            table_id=table.table_id,
            row_label=None,
            raw_value=raw_text,
            notes="pypdf baseline row parser",
        )
        parsed = parse_financial_row_text(
            raw_text,
            page_number=page_number,
            table_id=table.table_id,
            line_number=line_number,
            statement_type=resolved_statement_type,
            source_trace=source_trace,
        )
        if parsed is None:
            continue
        if parsed.source_trace is not None:
            parsed.source_trace.row_label = parsed.label
        parsed_rows.append(parsed)

    return parsed_rows


def parse_financial_rows_from_tables(
    tables: list[ExtractedFinancialTable],
) -> list[ParsedFinancialRow]:
    parsed_rows: list[ParsedFinancialRow] = []
    for table in tables:
        parsed_rows.extend(parse_financial_rows_from_table(table))
    return parsed_rows
