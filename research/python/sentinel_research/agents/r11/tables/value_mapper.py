from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from sentinel_research.agents.r11.schemas import (
    FinancialStatementType,
    MetricUnit,
    NormalizedFinancialLineItem,
    SourceTrace,
)


class R11ValueMappingError(ValueError):
    """Raised when normalized financial values cannot be parsed or mapped."""


class ParsedFinancialValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: str | int | float | None
    value: float | None
    is_missing: bool = False
    is_percent: bool = False
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class MappedLineItemValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    original_label: str
    statement_type: FinancialStatementType
    unit: MetricUnit = MetricUnit.UNKNOWN
    raw_period_values: dict[str, str | int | float | None]
    mapped_values: dict[str, ParsedFinancialValue]
    source_trace: SourceTrace | None = None
    notes: str | None = None

    @field_validator("canonical_name", "original_label")
    @classmethod
    def _validate_required_text(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("mapped_values")
    @classmethod
    def _validate_mapped_values(
        cls,
        value: dict[str, ParsedFinancialValue],
    ) -> dict[str, ParsedFinancialValue]:
        if not value:
            raise ValueError("mapped_values must not be empty")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


COMB_SIX_COLUMN_MAP: dict[str, str] = {
    "value_1": "group_current",
    "value_2": "group_previous",
    "value_3": "group_reported_change_percent",
    "value_4": "bank_current",
    "value_5": "bank_previous",
    "value_6": "bank_reported_change_percent",
}
COMB_FOUR_COLUMN_DUAL_SCOPE_MAP: dict[str, str] = {
    "value_1": "group_current",
    "value_2": "group_previous",
    "value_3": "bank_current",
    "value_4": "bank_previous",
}

_COMB_SIX_COLUMN_PERCENT_KEYS = {
    "group_reported_change_percent",
    "bank_reported_change_percent",
}
_PARENTHESIZED_NEGATIVE_PATTERN = re.compile(r"^\(\s*([0-9][0-9,]*\.?[0-9]*)\s*\)$")
_NUMERIC_PATTERN = re.compile(r"^[0-9][0-9,]*\.?[0-9]*,?$")


def parse_financial_value(
    raw: str | int | float | None,
    *,
    is_percent: bool = False,
) -> ParsedFinancialValue:
    if raw is None:
        return ParsedFinancialValue(
            raw=raw,
            value=None,
            is_missing=True,
            is_percent=is_percent,
        )

    if isinstance(raw, bool):
        raise R11ValueMappingError("boolean values are not valid financial values")

    if isinstance(raw, (int, float)):
        return ParsedFinancialValue(
            raw=raw,
            value=float(raw),
            is_missing=False,
            is_percent=is_percent,
        )

    text = raw.strip()
    if not text or text == "-":
        return ParsedFinancialValue(
            raw=raw,
            value=None,
            is_missing=True,
            is_percent=is_percent,
        )

    negative_match = _PARENTHESIZED_NEGATIVE_PATTERN.fullmatch(text)
    if negative_match is not None:
        numeric_text = negative_match.group(1).replace(",", "")
        return ParsedFinancialValue(
            raw=raw,
            value=-float(numeric_text),
            is_missing=False,
            is_percent=is_percent,
        )

    if not _NUMERIC_PATTERN.fullmatch(text):
        raise R11ValueMappingError(f"invalid financial value: {raw!r}")

    normalized = text[:-1] if text.endswith(",") else text
    normalized = normalized.replace(",", "")
    return ParsedFinancialValue(
        raw=raw,
        value=float(normalized),
        is_missing=False,
        is_percent=is_percent,
    )


def parse_period_values(
    period_values: dict[str, str | int | float | None],
    percent_keys: set[str] | None = None,
) -> dict[str, ParsedFinancialValue]:
    parsed_values: dict[str, ParsedFinancialValue] = {}
    percent_keys = percent_keys or set()
    for key, raw_value in period_values.items():
        parsed_values[key] = parse_financial_value(
            raw_value,
            is_percent=key in percent_keys,
        )
    return parsed_values


def map_comb_six_column_values(
    item: NormalizedFinancialLineItem,
) -> MappedLineItemValues:
    if "value_1" not in item.period_values or "value_2" not in item.period_values:
        raise R11ValueMappingError(
            f"{item.canonical_name} is missing required value_1/value_2 fields"
        )

    value_map, layout_note = _select_comb_value_map(item.period_values)
    mapped_period_values: dict[str, str | int | float | None] = {}
    for raw_key, semantic_key in value_map.items():
        if raw_key not in item.period_values:
            continue
        mapped_period_values[semantic_key] = item.period_values[raw_key]

    parsed_values = parse_period_values(
        mapped_period_values,
        percent_keys=_COMB_SIX_COLUMN_PERCENT_KEYS,
    )

    return MappedLineItemValues(
        canonical_name=item.canonical_name,
        original_label=item.original_label,
        statement_type=item.statement_type,
        unit=item.unit,
        raw_period_values=dict(item.period_values),
        mapped_values=parsed_values,
        source_trace=item.source_trace,
        notes=layout_note,
    )


def map_comb_six_column_items(
    items: list[NormalizedFinancialLineItem],
) -> list[MappedLineItemValues]:
    mapped_items: list[MappedLineItemValues] = []
    for item in items:
        if "value_1" not in item.period_values or "value_2" not in item.period_values:
            continue
        mapped_items.append(map_comb_six_column_values(item))
    return mapped_items


def get_required_numeric(mapped: MappedLineItemValues, key: str) -> float:
    if key not in mapped.mapped_values:
        raise R11ValueMappingError(
            f"{mapped.canonical_name} is missing mapped value for {key}"
        )

    parsed_value = mapped.mapped_values[key]
    if parsed_value.value is None:
        raise R11ValueMappingError(
            f"{mapped.canonical_name} has no numeric value for {key}"
        )

    return parsed_value.value


def _select_comb_value_map(
    period_values: dict[str, str | int | float | None],
) -> tuple[dict[str, str], str]:
    has_value_3 = "value_3" in period_values
    has_value_4 = "value_4" in period_values
    has_value_5 = "value_5" in period_values
    has_value_6 = "value_6" in period_values

    # Four-value rows are dual-scope current/previous layouts, not percent-bearing rows.
    if has_value_3 and has_value_4 and not has_value_5 and not has_value_6:
        return COMB_FOUR_COLUMN_DUAL_SCOPE_MAP, "comb_four_column_dual_scope_layout"
    return COMB_SIX_COLUMN_MAP, "comb_six_column_layout"
