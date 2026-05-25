from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_UNSAFE_TRADING_PATTERN = re.compile(
    r"\b(?:buy|sell|hold|target\s+price|place\s+order|entry|exit)\b",
    re.IGNORECASE,
)


def _normalize_required_str(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_snake_case(value: str) -> str:
    normalized = re.sub(r"[\s-]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def _normalize_str_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in values:
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def _require_timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _check_unsafe_trading_language(value: str, field_name: str) -> None:
    if _UNSAFE_TRADING_PATTERN.search(value):
        raise ValueError(f"{field_name} contains unsafe trading recommendation language")


class R11DocumentType(str, Enum):
    INTERIM_FINANCIAL_STATEMENT = "INTERIM_FINANCIAL_STATEMENT"
    ANNUAL_REPORT = "ANNUAL_REPORT"
    EARNINGS_RELEASE = "EARNINGS_RELEASE"
    FINANCIAL_REVIEW = "FINANCIAL_REVIEW"
    CORPORATE_DISCLOSURE = "CORPORATE_DISCLOSURE"
    OTHER = "OTHER"


class R11Sector(str, Enum):
    BANKING = "BANKING"
    INSURANCE = "INSURANCE"
    DIVERSIFIED = "DIVERSIFIED"
    MANUFACTURING = "MANUFACTURING"
    TOURISM = "TOURISM"
    CONSUMER = "CONSUMER"
    TELECOM = "TELECOM"
    ENERGY = "ENERGY"
    REAL_ESTATE = "REAL_ESTATE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class FinancialStatementType(str, Enum):
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    CASH_FLOW = "CASH_FLOW"
    EQUITY_STATEMENT = "EQUITY_STATEMENT"
    BANKING_KEY_METRICS = "BANKING_KEY_METRICS"
    NOTES = "NOTES"
    UNKNOWN = "UNKNOWN"


class MetricDirection(str, Enum):
    IMPROVING = "IMPROVING"
    DETERIORATING = "DETERIORATING"
    STABLE = "STABLE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class MetricUnit(str, Enum):
    LKR = "LKR"
    LKR_MILLION = "LKR_MILLION"
    LKR_BILLION = "LKR_BILLION"
    PERCENT = "PERCENT"
    RATIO = "RATIO"
    BASIS_POINTS = "BASIS_POINTS"
    COUNT = "COUNT"
    TEXT = "TEXT"
    UNKNOWN = "UNKNOWN"


class RedFlagSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class R11ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SourceTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    local_file_path: str | None = None
    ticker: str | None = None
    company: str | None = None
    announcement_id: int | str | None = None
    page_number: int | None = None
    table_id: str | None = None
    row_label: str | None = None
    column_label: str | None = None
    raw_value: str | int | float | None = None
    extracted_value: str | int | float | None = None
    notes: str | None = None

    @field_validator(
        "source_document_id",
        "source_type",
        "source_url",
        "local_file_path",
        "company",
        "table_id",
        "row_label",
        "column_label",
        "notes",
        mode="before",
    )
    @classmethod
    def _strip_optional_str_fields(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("announcement_id", mode="before")
    @classmethod
    def _normalize_announcement_id(cls, value: int | str | None) -> int | str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized if normalized else None
        return value

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_str(value)
        return normalized.upper() if normalized else None

    @field_validator("page_number")
    @classmethod
    def _validate_page_number(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("page_number must be positive")
        return value


class ExtractedFinancialTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN
    title: str | None = None
    page_number: int | None = None
    columns: list[str]
    rows: list[dict[str, str | int | float | None]]
    extraction_method: str | None = None
    extraction_confidence: R11ConfidenceLevel = R11ConfidenceLevel.MEDIUM
    source_trace: SourceTrace | None = None

    @field_validator("table_id")
    @classmethod
    def _validate_table_id(cls, value: str) -> str:
        return _normalize_required_str(value, "table_id")

    @field_validator("title", "extraction_method", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("page_number")
    @classmethod
    def _validate_page_number(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("page_number must be positive")
        return value

    @field_validator("columns")
    @classmethod
    def _normalize_columns(cls, value: list[str]) -> list[str]:
        normalized = _normalize_str_list(value)
        if not normalized:
            raise ValueError("columns must not be empty")
        return normalized

    @field_validator("rows")
    @classmethod
    def _validate_rows(cls, value: list[dict[str, str | int | float | None]]) -> list[dict[str, str | int | float | None]]:
        if not value:
            raise ValueError("rows must not be empty")
        return value


class NormalizedFinancialLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    original_label: str
    statement_type: FinancialStatementType
    period_values: dict[str, int | float | str | None]
    unit: MetricUnit = MetricUnit.UNKNOWN
    source_trace: SourceTrace | None = None
    normalization_confidence: R11ConfidenceLevel = R11ConfidenceLevel.MEDIUM

    @field_validator("canonical_name")
    @classmethod
    def _normalize_canonical_name(cls, value: str) -> str:
        normalized = _normalize_snake_case(value)
        if not normalized:
            raise ValueError("canonical_name must not be empty")
        return normalized

    @field_validator("original_label")
    @classmethod
    def _validate_original_label(cls, value: str) -> str:
        return _normalize_required_str(value, "original_label")

    @field_validator("period_values")
    @classmethod
    def _validate_period_values(
        cls,
        value: dict[str, int | float | str | None],
    ) -> dict[str, int | float | str | None]:
        if not value:
            raise ValueError("period_values must not be empty")
        return value


class NormalizedFinancialStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_id: str
    ticker: str
    company: str
    sector: R11Sector = R11Sector.UNKNOWN
    document_type: R11DocumentType
    period_label: str | None = None
    statement_type: FinancialStatementType = FinancialStatementType.UNKNOWN
    line_items: list[NormalizedFinancialLineItem]
    source_trace: SourceTrace | None = None

    @field_validator("statement_id", "company")
    @classmethod
    def _validate_required_text(cls, value: str, info) -> str:
        return _normalize_required_str(value, info.field_name)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return _normalize_required_str(value, "ticker").upper()

    @field_validator("period_label", mode="before")
    @classmethod
    def _normalize_period_label(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("line_items")
    @classmethod
    def _validate_line_items(
        cls,
        value: list[NormalizedFinancialLineItem],
    ) -> list[NormalizedFinancialLineItem]:
        if not value:
            raise ValueError("line_items must not be empty")
        return value


class ToolAuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_version: str | None = None
    operation: str
    metric_name: str | None = None
    formula: str | None = None
    inputs: dict[str, int | float | str | None] = Field(default_factory=dict)
    output: int | float | str | None = None
    verified: bool = True
    generated_at: datetime
    source_traces: list[SourceTrace] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("tool_name", "operation")
    @classmethod
    def _validate_required_text(cls, value: str, info) -> str:
        return _normalize_required_str(value, info.field_name)

    @field_validator("tool_version", "metric_name", "formula", "notes", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("generated_at")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, "generated_at")


class FinancialMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    display_name: str | None = None
    value: int | float | str | None
    unit: MetricUnit = MetricUnit.UNKNOWN
    period: str | None = None
    comparison_period: str | None = None
    direction: MetricDirection = MetricDirection.UNKNOWN
    calculation_audit_id: str | None = None
    source_traces: list[SourceTrace] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("metric_name")
    @classmethod
    def _normalize_metric_name(cls, value: str) -> str:
        normalized = _normalize_snake_case(value)
        if not normalized:
            raise ValueError("metric_name must not be empty")
        return normalized

    @field_validator(
        "display_name",
        "period",
        "comparison_period",
        "calculation_audit_id",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)


class FundamentalScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    earnings_quality: MetricDirection = MetricDirection.UNKNOWN
    revenue_trend: MetricDirection = MetricDirection.UNKNOWN
    margin_trend: MetricDirection = MetricDirection.UNKNOWN
    balance_sheet_risk: R11ConfidenceLevel | None = None
    cash_flow_quality: MetricDirection = MetricDirection.UNKNOWN
    capital_strength: R11ConfidenceLevel | None = None
    accounting_risk: RedFlagSeverity | None = None
    manual_review_required: bool = False
    summary: str | None = None

    @field_validator("summary", mode="before")
    @classmethod
    def _normalize_summary(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_str(value)
        if normalized is not None:
            _check_unsafe_trading_language(normalized, "summary")
        return normalized


class AccountingRedFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    red_flag_id: str
    category: str
    severity: RedFlagSeverity
    description: str
    source_traces: list[SourceTrace] = Field(default_factory=list)
    manual_review_required: bool = True

    @field_validator("red_flag_id")
    @classmethod
    def _validate_red_flag_id(cls, value: str) -> str:
        return _normalize_required_str(value, "red_flag_id")

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, value: str) -> str:
        normalized = _normalize_required_str(value, "category")
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
        if not normalized:
            raise ValueError("category must not be empty")
        return normalized

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        normalized = _normalize_required_str(value, "description")
        _check_unsafe_trading_language(normalized, "description")
        return normalized


class R11AnalystDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "r11_analyst_dossier_v1"
    dossier_id: str
    generated_at: datetime
    ticker: str
    company: str
    sector: R11Sector = R11Sector.UNKNOWN
    document_type: R11DocumentType
    period_label: str | None = None
    source_traces: list[SourceTrace]
    extracted_tables: list[ExtractedFinancialTable] = Field(default_factory=list)
    normalized_statements: list[NormalizedFinancialStatement] = Field(default_factory=list)
    financial_metrics: list[FinancialMetric] = Field(default_factory=list)
    fundamental_scorecard: FundamentalScorecard
    accounting_red_flags: list[AccountingRedFlag] = Field(default_factory=list)
    tool_audit: list[ToolAuditEntry] = Field(default_factory=list)
    analyst_summary: str | None = None
    confidence: R11ConfidenceLevel = R11ConfidenceLevel.MEDIUM
    manual_review_required: bool = False
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "r11_analyst_dossier_v1":
            raise ValueError(
                f'schema_version must be "r11_analyst_dossier_v1", got {value!r}'
            )
        return value

    @field_validator("dossier_id", "company")
    @classmethod
    def _validate_required_text(cls, value: str, info) -> str:
        return _normalize_required_str(value, info.field_name)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return _normalize_required_str(value, "ticker").upper()

    @field_validator("generated_at")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, "generated_at")

    @field_validator("period_label", "analyst_summary", "notes", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None, info) -> str | None:
        normalized = _normalize_optional_str(value)
        if normalized is not None and info.field_name in {"analyst_summary", "notes"}:
            _check_unsafe_trading_language(normalized, info.field_name)
        return normalized

    @field_validator("source_traces")
    @classmethod
    def _validate_source_traces(cls, value: list[SourceTrace]) -> list[SourceTrace]:
        if not value:
            raise ValueError("source_traces must not be empty")
        return value

    @model_validator(mode="after")
    def _enforce_review_guards(self) -> R11AnalystDossier:
        has_high_risk_red_flag = any(
            red_flag.severity in {RedFlagSeverity.HIGH, RedFlagSeverity.CRITICAL}
            for red_flag in self.accounting_red_flags
        )
        has_calculated_metrics_without_audit = bool(self.financial_metrics) and not self.tool_audit and any(
            metric.metric_name.endswith(("_growth", "_margin", "_ratio", "_change"))
            for metric in self.financial_metrics
        )

        if has_high_risk_red_flag or has_calculated_metrics_without_audit:
            self.manual_review_required = True

        return self


def build_dossier_id(
    ticker: str,
    generated_at: datetime,
    period_label: str | None = None,
) -> str:
    normalized_ticker = _normalize_required_str(ticker, "ticker").upper()
    generated_at = _require_timezone_aware(generated_at, "generated_at")
    timestamp = generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    dossier_id = f"r11_dossier_{normalized_ticker}_{timestamp}"

    if period_label is None:
        return dossier_id

    normalized_period = _SAFE_ID_PATTERN.sub("_", period_label.strip()).strip("_")
    if not normalized_period:
        return dossier_id

    return f"{dossier_id}_{normalized_period}"
