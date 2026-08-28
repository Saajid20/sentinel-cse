from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.schemas import (
    ExtractedFinancialTable,
    FinancialStatementType,
    SourceTrace,
)

_VALUE_TOKEN_PATTERN = re.compile(
    r"^(?:(?:\d[\d,]*(?:\.\d+)?)|(?:\(\d[\d,]*(?:\.\d+)?\))|-|(?:Rs\.\d[\d,]*(?:\.\d+)?))$",
    re.IGNORECASE,
)
_STRIPPABLE_VALUE_TOKEN_PATTERN = re.compile(
    r"^(?:(?:\d[\d,]*(?:\.\d+)?)|(?:\(\d[\d,]*(?:\.\d+)?\))|(?:-?\d[\d,]*(?:\.\d+)?%)|(?:\(-?\d[\d,]*(?:\.\d+)?%\))|-|(?:Rs\.\d[\d,]*(?:\.\d+)?))$",
    re.IGNORECASE,
)
# pypdf sometimes emits a parenthesised percent cell with an internal space, so
# "(63%)" arrives as "( 63%)" and tokenizes as "(" + "63%)". Neither half matches
# _STRIPPABLE_VALUE_TOKEN_PATTERN, which strands the whole row tail inside the label.
# This collapses only that pypdf-inserted space, and only for label derivation.
_SPLIT_PERCENT_CELL_PATTERN = re.compile(r"\(\s+(?=-?\d[\d,]*(?:\.\d+)?%\))")
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


def _collapse_split_percent_cells(text: str) -> str:
    """Rejoin pypdf-split parenthesised percent cells: "( 63%)" -> "(63%)".

    Label-derivation helper only. It never widens value recognition: percent cells
    are not financial values, and raw_text is left untouched for source-trace fidelity.
    """
    return _SPLIT_PERCENT_CELL_PATTERN.sub("(", text)


def strip_numeric_tokens_from_label(text: str, values: list[str]) -> str:
    if not values:
        return re.sub(r"\s+", " ", text.strip())

    tokens = re.split(r"\s+", text.strip())
    trailing_value_count = 0
    for token in reversed(tokens):
        if _STRIPPABLE_VALUE_TOKEN_PATTERN.fullmatch(token):
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

    label = strip_numeric_tokens_from_label(
        _collapse_split_percent_cells(normalized_text),
        values,
    )
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


def is_wrapped_label_prefix_line(text: str) -> bool:
    """True when a line is the first half of a caption wrapped across two lines.

    Three conditions, all structural. The line carries no financial value at
    all; it is not a statement or period header; and its final word begins with
    a lowercase letter. That last test is what separates a caption cut
    mid-phrase ("Total Equity attributable to the equity") from a complete
    section heading, because CSE statements title-case their headings
    ("Equity and Liabilities", "Non-Current Assets", "ASSETS") and so always end
    them on a capitalised word.
    """
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return False
    if parse_numeric_tokens(normalized):
        return False

    upper_text = normalized.upper()
    if _DATE_HEADER_PATTERN.search(upper_text):
        return False
    if any(phrase in upper_text for phrase in _HEADER_PHRASES):
        return False

    tokens = normalized.split(" ")
    if len(tokens) < 2:
        return False
    return tokens[-1][:1].islower()


def is_wrapped_label_continuation(label: str) -> bool:
    """True when a row label reads as the tail of a caption wrapped mid-phrase.

    The mirror of :func:`is_wrapped_label_prefix_line`: a parsed row whose label
    begins with a lowercase letter did not start where the caption started, so
    the first half is sitting on the line above. Requiring lowercase on both
    sides of the break is what keeps the join anchored to an actual wrap point.
    """
    stripped = label.strip()
    return bool(stripped) and stripped[0].islower()


def parse_financial_rows_from_table(
    table: ExtractedFinancialTable,
    *,
    statement_type: FinancialStatementType | None = None,
) -> list[ParsedFinancialRow]:
    parsed_rows: list[ParsedFinancialRow] = []
    resolved_statement_type = statement_type or table.statement_type
    page_number = table.page_number or 0
    previous_line: tuple[int, str] | None = None

    for row in table.rows:
        line_number = int(row.get("line_number", 0))
        raw_text = str(row.get("text", "")).strip()

        parsed = _parse_row_with_source_trace(
            raw_text,
            table=table,
            page_number=page_number,
            line_number=line_number,
            statement_type=resolved_statement_type,
            joined_from_line_number=None,
        )

        joined = _recover_wrapped_label_row(
            parsed,
            previous_line=previous_line,
            raw_text=raw_text,
            table=table,
            page_number=page_number,
            line_number=line_number,
            statement_type=resolved_statement_type,
        )
        if joined is not None:
            parsed = joined

        previous_line = (line_number, raw_text)
        if parsed is None:
            continue
        parsed_rows.append(parsed)

    return parsed_rows


def _recover_wrapped_label_row(
    parsed: ParsedFinancialRow | None,
    *,
    previous_line: tuple[int, str] | None,
    raw_text: str,
    table: ExtractedFinancialTable,
    page_number: int,
    line_number: int,
    statement_type: FinancialStatementType,
) -> ParsedFinancialRow | None:
    """Rejoin a balance-sheet caption that pypdf wrapped across two lines.

    HVA.N0000 page 5 emits its group equity row as::

        29: Total Equity attributable to the equity
        30: holders of the Company/Total equity (64,290,676) (70,799,910) ...

    Line 29 carries no values so it is dropped, and line 30 alone yields the
    label "holders of the Company/Total equity", which names nothing. This is
    the inverse of the WIND block layout: there the values are stranded, here
    the label is.

    The recovery is a continuation JOIN of the label line to its value line. It
    is deliberately not an alias for the truncated fragment -- aliasing
    "holders of the company total equity" would promote a page-layout accident
    to a canonical financial name, and the next issuer that wraps at a
    different word would need another one.

    Scoped to BALANCE_SHEET pages, following CLAUDE.md's ordering, which puts
    statement-type filtering ahead of layout-specific recovery. Income
    statements in this corpus wrap their other-comprehensive-income captions
    the same way, but no metric depends on those rows and no case has been
    demonstrated for them, so they are left alone.

    Returns None when no join applies, so the caller keeps the unjoined row.
    """
    if statement_type is not FinancialStatementType.BALANCE_SHEET:
        return None
    if parsed is None or not is_wrapped_label_continuation(parsed.label):
        return None
    if previous_line is None:
        return None

    previous_line_number, previous_text = previous_line
    if previous_line_number + 1 != line_number:
        return None
    if not is_wrapped_label_prefix_line(previous_text):
        return None

    normalized_prefix = re.sub(r"\s+", " ", previous_text.strip())
    joined_text = normalized_prefix + " " + raw_text
    # A join must never remove a row the unjoined line already produced, so a
    # failed re-parse falls back to the caller's original row.
    return _parse_row_with_source_trace(
        joined_text,
        table=table,
        page_number=page_number,
        line_number=line_number,
        statement_type=statement_type,
        joined_from_line_number=previous_line_number,
    )


def _parse_row_with_source_trace(
    text: str,
    *,
    table: ExtractedFinancialTable,
    page_number: int,
    line_number: int,
    statement_type: FinancialStatementType,
    joined_from_line_number: int | None,
) -> ParsedFinancialRow | None:
    notes = "pypdf baseline row parser"
    if joined_from_line_number is not None:
        notes = (
            "pypdf baseline row parser; wrapped label continuation join from "
            f"line {joined_from_line_number}"
        )
    source_trace = SourceTrace(
        local_file_path=table.source_trace.local_file_path if table.source_trace else None,
        page_number=table.page_number,
        table_id=table.table_id,
        row_label=None,
        raw_value=text,
        notes=notes,
    )
    parsed = parse_financial_row_text(
        text,
        page_number=page_number,
        table_id=table.table_id,
        line_number=line_number,
        statement_type=statement_type,
        source_trace=source_trace,
    )
    if parsed is not None and parsed.source_trace is not None:
        parsed.source_trace.row_label = parsed.label
    return parsed


def parse_financial_rows_from_tables(
    tables: list[ExtractedFinancialTable],
) -> list[ParsedFinancialRow]:
    parsed_rows: list[ParsedFinancialRow] = []
    for table in tables:
        parsed_rows.extend(parse_financial_rows_from_table(table))
    return parsed_rows
