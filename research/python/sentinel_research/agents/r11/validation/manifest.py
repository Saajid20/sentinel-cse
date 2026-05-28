from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sentinel_research.agents.r11.schemas import FinancialStatementType

_SAFE_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")


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


def _normalize_safe_id(value: str, field_name: str) -> str:
    normalized = _normalize_required_str(value, field_name).lower()
    normalized = re.sub(r"[\s-]+", "_", normalized)
    normalized = _SAFE_ID_PATTERN.sub("_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class R11ValidationManifestError(ValueError):
    """Raised when an R11 validation manifest cannot be loaded or saved safely."""


class ExpectedStatementPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    statement_type: FinancialStatementType

    @field_validator("page_number")
    @classmethod
    def _validate_page_number(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("page_number must be positive")
        return value


class R11ValidationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    ticker: str | None = None
    company_name: str | None = None
    description: str | None = None
    analysis_json_path: str
    expected_pages: list[ExpectedStatementPage] = Field(default_factory=list)
    min_verified_metrics: int | None = None
    min_aggregated_metrics: int | None = None
    expect_manual_review: bool | None = None
    require_scorecard: bool = True
    require_no_conflicts: bool = True
    notes: str | None = None

    @field_validator("case_id")
    @classmethod
    def _normalize_case_id(cls, value: str) -> str:
        return _normalize_safe_id(value, "case_id")

    @field_validator("analysis_json_path")
    @classmethod
    def _validate_analysis_json_path(cls, value: str) -> str:
        return _normalize_required_str(value, "analysis_json_path")

    @field_validator(
        "ticker",
        "company_name",
        "description",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("min_verified_metrics", "min_aggregated_metrics")
    @classmethod
    def _validate_non_negative_minimum(
        cls,
        value: int | None,
        info,
    ) -> int | None:
        if value is not None and value < 0:
            raise ValueError(f"{info.field_name} must be >= 0")
        return value


class R11ValidationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "r11_validation_manifest_v1"
    cases: list[R11ValidationCase]
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "r11_validation_manifest_v1":
            raise ValueError(
                'schema_version must be "r11_validation_manifest_v1"'
            )
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("cases")
    @classmethod
    def _validate_cases(cls, value: list[R11ValidationCase]) -> list[R11ValidationCase]:
        if not value:
            raise ValueError("cases must not be empty")
        seen: set[str] = set()
        for item in value:
            if item.case_id in seen:
                raise ValueError(f"duplicate case_id: {item.case_id}")
            seen.add(item.case_id)
        return value


def load_validation_manifest(path: str | Path) -> R11ValidationManifest:
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists() or not manifest_path.is_file():
        raise R11ValidationManifestError(
            f"Validation manifest path does not exist: {manifest_path}"
        )

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise R11ValidationManifestError(
            f"Validation manifest JSON is invalid: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise R11ValidationManifestError("Validation manifest payload must be an object")

    try:
        return R11ValidationManifest.model_validate(payload)
    except ValueError as error:
        raise R11ValidationManifestError(
            f"Validation manifest is invalid: {error}"
        ) from error


def save_validation_manifest(
    manifest: R11ValidationManifest,
    path: str | Path,
) -> None:
    manifest_path = Path(path).expanduser()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
        newline="\n",
    )


def validation_case_to_cli_args(case: R11ValidationCase) -> list[str]:
    args = ["--analysis-json", case.analysis_json_path]

    for expected_page in case.expected_pages:
        args.extend(
            [
                "--expect-page",
                f"{expected_page.page_number}:{expected_page.statement_type.value}",
            ]
        )

    if case.min_verified_metrics is not None:
        args.extend(["--min-verified-metrics", str(case.min_verified_metrics)])

    if case.min_aggregated_metrics is not None:
        args.extend(["--min-aggregated-metrics", str(case.min_aggregated_metrics)])

    if case.expect_manual_review is not None:
        args.extend(
            [
                "--expect-manual-review",
                "true" if case.expect_manual_review else "false",
            ]
        )

    if case.require_scorecard:
        args.append("--require-scorecard")

    if case.require_no_conflicts:
        args.append("--require-no-conflicts")

    return args


__all__ = [
    "R11ValidationManifestError",
    "ExpectedStatementPage",
    "R11ValidationCase",
    "R11ValidationManifest",
    "load_validation_manifest",
    "save_validation_manifest",
    "validation_case_to_cli_args",
]
