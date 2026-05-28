from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


def _normalize_identifier(value: str, field_name: str) -> str:
    normalized = _normalize_required_str(value, field_name).lower()
    normalized = re.sub(r"[\s-]+", "_", normalized)
    normalized = _SAFE_ID_PATTERN.sub("_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class R11ValidationChecklistError(ValueError):
    """Raised when a checklist or its results cannot be evaluated deterministically."""


class ChecklistItemLevel(str, Enum):
    REQUIRED = "REQUIRED"
    ADVISORY = "ADVISORY"


class ChecklistResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ASSESSED = "NOT_ASSESSED"


class ChecklistEvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PdfValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int | None = None
    table_id: str | None = None
    locator_text: str | None = None
    note: str | None = None

    @field_validator("table_id", "locator_text", "note", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("page_number")
    @classmethod
    def _validate_page_number(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("page_number must be positive")
        return value

    @model_validator(mode="after")
    def _require_locator(self) -> PdfValidationEvidence:
        if self.page_number is None and self.table_id is None and self.locator_text is None:
            raise ValueError("validation evidence must include page_number, table_id, or locator_text")
        return self


class PdfValidationChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    title: str
    description: str | None = None
    level: ChecklistItemLevel = ChecklistItemLevel.REQUIRED
    tags: list[str] = Field(default_factory=list)

    @field_validator("item_id")
    @classmethod
    def _normalize_item_id(cls, value: str) -> str:
        return _normalize_identifier(value, "item_id")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _normalize_required_str(value, "title")

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            tag = _normalize_identifier(item, "tag")
            if tag not in normalized:
                normalized.append(tag)
        return normalized


class PdfValidationChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checklist_id: str
    version: str = "r11_pdf_validation_checklist_v1"
    title: str
    items: list[PdfValidationChecklistItem]

    @field_validator("checklist_id")
    @classmethod
    def _normalize_checklist_id(cls, value: str) -> str:
        return _normalize_identifier(value, "checklist_id")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _normalize_required_str(value, "title")

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return _normalize_required_str(value, "version")

    @field_validator("items")
    @classmethod
    def _validate_items(cls, value: list[PdfValidationChecklistItem]) -> list[PdfValidationChecklistItem]:
        if not value:
            raise ValueError("items must not be empty")
        seen: set[str] = set()
        for item in value:
            if item.item_id in seen:
                raise ValueError(f"duplicate checklist item_id: {item.item_id}")
            seen.add(item.item_id)
        return value


class PdfValidationChecklistResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: ChecklistResultStatus
    notes: str | None = None
    evidence: list[PdfValidationEvidence] = Field(default_factory=list)

    @field_validator("item_id")
    @classmethod
    def _normalize_item_id(cls, value: str) -> str:
        return _normalize_identifier(value, "item_id")

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)


class PdfValidationItemEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    title: str
    level: ChecklistItemLevel
    status: ChecklistResultStatus
    satisfied: bool
    notes: str | None = None
    evidence: list[PdfValidationEvidence] = Field(default_factory=list)


class PdfValidationChecklistEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checklist_id: str
    checklist_version: str
    overall_status: ChecklistEvaluationStatus
    total_items: int
    passed_items: int
    failed_items: int
    manual_review_items: int
    not_applicable_items: int
    not_assessed_items: int
    missing_required_item_ids: list[str] = Field(default_factory=list)
    failing_item_ids: list[str] = Field(default_factory=list)
    manual_review_item_ids: list[str] = Field(default_factory=list)
    advisory_issue_item_ids: list[str] = Field(default_factory=list)
    evaluations: list[PdfValidationItemEvaluation]

    @field_validator("evaluations")
    @classmethod
    def _validate_evaluations(cls, value: list[PdfValidationItemEvaluation]) -> list[PdfValidationItemEvaluation]:
        if not value:
            raise ValueError("evaluations must not be empty")
        return value


def evaluate_pdf_validation_checklist(
    checklist: PdfValidationChecklist,
    results: list[PdfValidationChecklistResult],
) -> PdfValidationChecklistEvaluation:
    result_map: dict[str, PdfValidationChecklistResult] = {}

    for result in results:
        if result.item_id in result_map:
            raise R11ValidationChecklistError(f"duplicate result item_id: {result.item_id}")
        result_map[result.item_id] = result

    known_item_ids = {item.item_id for item in checklist.items}
    unexpected_item_ids = sorted(item_id for item_id in result_map if item_id not in known_item_ids)
    if unexpected_item_ids:
        joined = ", ".join(unexpected_item_ids)
        raise R11ValidationChecklistError(f"unexpected result item_id(s): {joined}")

    evaluations: list[PdfValidationItemEvaluation] = []
    missing_required_item_ids: list[str] = []
    failing_item_ids: list[str] = []
    manual_review_item_ids: list[str] = []
    advisory_issue_item_ids: list[str] = []

    status_counts = {
        ChecklistResultStatus.PASS: 0,
        ChecklistResultStatus.FAIL: 0,
        ChecklistResultStatus.MANUAL_REVIEW: 0,
        ChecklistResultStatus.NOT_APPLICABLE: 0,
        ChecklistResultStatus.NOT_ASSESSED: 0,
    }

    overall_status = ChecklistEvaluationStatus.PASS

    for item in checklist.items:
        result = result_map.get(item.item_id)
        if result is None:
            status = ChecklistResultStatus.NOT_ASSESSED
            notes = "No validation result provided."
            evidence: list[PdfValidationEvidence] = []
        else:
            status = result.status
            notes = result.notes
            evidence = list(result.evidence)

        status_counts[status] += 1
        satisfied = status in {
            ChecklistResultStatus.PASS,
            ChecklistResultStatus.NOT_APPLICABLE,
        }

        evaluations.append(
            PdfValidationItemEvaluation(
                item_id=item.item_id,
                title=item.title,
                level=item.level,
                status=status,
                satisfied=satisfied,
                notes=notes,
                evidence=evidence,
            )
        )

        if item.level is ChecklistItemLevel.REQUIRED:
            if status in {ChecklistResultStatus.FAIL, ChecklistResultStatus.NOT_APPLICABLE, ChecklistResultStatus.NOT_ASSESSED}:
                failing_item_ids.append(item.item_id)
                if status is ChecklistResultStatus.NOT_ASSESSED:
                    missing_required_item_ids.append(item.item_id)
                overall_status = ChecklistEvaluationStatus.FAIL
            elif status is ChecklistResultStatus.MANUAL_REVIEW and overall_status is not ChecklistEvaluationStatus.FAIL:
                manual_review_item_ids.append(item.item_id)
                overall_status = ChecklistEvaluationStatus.MANUAL_REVIEW
        else:
            if status in {ChecklistResultStatus.FAIL, ChecklistResultStatus.MANUAL_REVIEW}:
                advisory_issue_item_ids.append(item.item_id)
                if status is ChecklistResultStatus.MANUAL_REVIEW:
                    manual_review_item_ids.append(item.item_id)
                if overall_status is ChecklistEvaluationStatus.PASS:
                    overall_status = ChecklistEvaluationStatus.MANUAL_REVIEW

        if status is ChecklistResultStatus.MANUAL_REVIEW and item.item_id not in manual_review_item_ids:
            manual_review_item_ids.append(item.item_id)

    return PdfValidationChecklistEvaluation(
        checklist_id=checklist.checklist_id,
        checklist_version=checklist.version,
        overall_status=overall_status,
        total_items=len(checklist.items),
        passed_items=status_counts[ChecklistResultStatus.PASS],
        failed_items=status_counts[ChecklistResultStatus.FAIL],
        manual_review_items=status_counts[ChecklistResultStatus.MANUAL_REVIEW],
        not_applicable_items=status_counts[ChecklistResultStatus.NOT_APPLICABLE],
        not_assessed_items=status_counts[ChecklistResultStatus.NOT_ASSESSED],
        missing_required_item_ids=missing_required_item_ids,
        failing_item_ids=failing_item_ids,
        manual_review_item_ids=manual_review_item_ids,
        advisory_issue_item_ids=advisory_issue_item_ids,
        evaluations=evaluations,
    )
