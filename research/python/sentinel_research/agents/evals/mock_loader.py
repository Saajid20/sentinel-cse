from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

_ANALYSIS_SCOPE_VALUES = ("MARKET", "SECTOR", "TICKER")
_MACRO_RISK_LEVEL_VALUES = ("LOW", "MEDIUM", "HIGH")
_SENTIMENT_VALUES = ("BULLISH", "BEARISH", "NEUTRAL", "MIXED")
_SIGNAL_POLICY_VALUES = ("SUPPORT", "BLOCK", "MANUAL_REVIEW", "NO_EFFECT")
_SOURCE_TYPE_VALUES = ("CBSL", "CSE_DISCLOSURE", "NEWS", "DAILY_FT", "OTHER")


class MockDocumentExpected(BaseModel):
    analysis_scope: Literal[*_ANALYSIS_SCOPE_VALUES] | None = None
    analysis_scope_any_of: list[Literal[*_ANALYSIS_SCOPE_VALUES]] = Field(default_factory=list)
    macro_risk_level: Literal[*_MACRO_RISK_LEVEL_VALUES] | None = None
    macro_risk_level_any_of: list[Literal[*_MACRO_RISK_LEVEL_VALUES]] = Field(default_factory=list)
    sentiment: Literal[*_SENTIMENT_VALUES] | None = None
    sentiment_any_of: list[Literal[*_SENTIMENT_VALUES]] = Field(default_factory=list)
    signal_policy: Literal[*_SIGNAL_POLICY_VALUES] | None = None
    signal_policy_any_of: list[Literal[*_SIGNAL_POLICY_VALUES]] = Field(default_factory=list)
    must_include_catalyst_tags: list[str] = Field(default_factory=list)
    catalyst_tag_any_of_groups: list[list[str]] = Field(default_factory=list)
    must_include_affected_sectors: list[str] = Field(default_factory=list)
    affected_sector_any_of_groups: list[list[str]] = Field(default_factory=list)
    manual_review_required: bool | None = None
    manual_review_required_any_of: list[bool] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_expectation_shape(self) -> "MockDocumentExpected":
        comparisons = (
            ("analysis_scope", self.analysis_scope, self.analysis_scope_any_of),
            ("macro_risk_level", self.macro_risk_level, self.macro_risk_level_any_of),
            ("sentiment", self.sentiment, self.sentiment_any_of),
            ("signal_policy", self.signal_policy, self.signal_policy_any_of),
            (
                "manual_review_required",
                self.manual_review_required,
                self.manual_review_required_any_of,
            ),
        )
        for field_name, exact_value, any_of_values in comparisons:
            if exact_value is None and not any_of_values:
                raise ValueError(
                    f"{field_name} or {field_name}_any_of must be provided"
                )
            if any_of_values and len(any_of_values) == 0:
                raise ValueError(f"{field_name}_any_of must not be empty")

        if not self.must_include_catalyst_tags and not self.catalyst_tag_any_of_groups:
            raise ValueError(
                "must_include_catalyst_tags or catalyst_tag_any_of_groups must be provided"
            )
        if self.catalyst_tag_any_of_groups:
            for group in self.catalyst_tag_any_of_groups:
                if not group:
                    raise ValueError("catalyst_tag_any_of_groups must not contain empty groups")

        if self.affected_sector_any_of_groups:
            for group in self.affected_sector_any_of_groups:
                if not group:
                    raise ValueError("affected_sector_any_of_groups must not contain empty groups")

        return self


class MockDocumentCase(BaseModel):
    id: str
    title: str
    source_type: Literal[*_SOURCE_TYPE_VALUES]
    url: str | None = None
    published_at: str | None = None
    document: str
    expected: MockDocumentExpected


def _default_mock_documents_path() -> Path:
    return Path(__file__).resolve().parent / "mock_documents" / "r10_mock_documents.jsonl"


def load_mock_documents(path: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_path = Path(path) if path is not None else _default_mock_documents_path()
    cases: list[dict[str, Any]] = []

    for line_number, raw_line in enumerate(
        resolved_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON in mock document file at line {line_number}: {error}"
            ) from error
        try:
            case = MockDocumentCase.model_validate(payload)
        except ValidationError as error:
            raise ValueError(
                f"Invalid mock document case at line {line_number}: {error}"
            ) from error
        case_data = case.model_dump(mode="python")
        case_data["expected"] = case.expected.model_dump(
            mode="python",
            exclude_none=True,
            exclude_defaults=True,
        )
        cases.append(case_data)

    return cases
