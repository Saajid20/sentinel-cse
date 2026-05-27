from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.validation import (  # noqa: E402
    ChecklistEvaluationStatus,
    ChecklistItemLevel,
    ChecklistResultStatus,
    PdfValidationChecklist,
    PdfValidationChecklistItem,
    PdfValidationChecklistResult,
    PdfValidationEvidence,
    R11ValidationChecklistError,
    evaluate_pdf_validation_checklist,
)


def make_checklist_item(**overrides: object) -> PdfValidationChecklistItem:
    payload = {
        "item_id": " has_income_statement ",
        "title": " Income statement located ",
        "description": "Core statement appears in the disclosure.",
        "level": "REQUIRED",
        "tags": [" statements ", " coverage "],
    }
    payload.update(overrides)
    return PdfValidationChecklistItem.model_validate(payload)


def make_checklist(**overrides: object) -> PdfValidationChecklist:
    payload = {
        "checklist_id": " q1_core_pdf_checks ",
        "title": " Q1 core PDF checks ",
        "items": [
            make_checklist_item(),
            make_checklist_item(
                item_id="has_balance_sheet",
                title="Balance sheet located",
            ),
            make_checklist_item(
                item_id="footnote_crosscheck",
                title="Footnote cross-check",
                level="ADVISORY",
            ),
        ],
    }
    payload.update(overrides)
    return PdfValidationChecklist.model_validate(payload)


def make_result(**overrides: object) -> PdfValidationChecklistResult:
    payload = {
        "item_id": " has_income_statement ",
        "status": "PASS",
        "notes": " statement detected ",
        "evidence": [
            {
                "page_number": 4,
                "locator_text": "Condensed Income Statement",
                "note": "title row",
            }
        ],
    }
    payload.update(overrides)
    return PdfValidationChecklistResult.model_validate(payload)


def test_checklist_item_and_result_normalize_ids_tags_and_notes() -> None:
    item = make_checklist_item(item_id=" Has Income-Statement ")
    result = make_result(item_id=" Has Income-Statement ", notes=" detected ")

    assert item.item_id == "has_income_statement"
    assert item.tags == ["statements", "coverage"]
    assert result.item_id == "has_income_statement"
    assert result.notes == "detected"


def test_evaluate_pdf_validation_checklist_returns_pass_for_clean_required_and_advisory_results() -> None:
    checklist = make_checklist()
    evaluation = evaluate_pdf_validation_checklist(
        checklist,
        [
            make_result(item_id="has_income_statement", status="PASS"),
            make_result(
                item_id="has_balance_sheet",
                status="PASS",
                evidence=[{"page_number": 6, "locator_text": "Statement of Financial Position"}],
            ),
            make_result(
                item_id="footnote_crosscheck",
                status="NOT_APPLICABLE",
                evidence=[{"table_id": "notes-1"}],
            ),
        ],
    )

    assert evaluation.overall_status is ChecklistEvaluationStatus.PASS
    assert evaluation.passed_items == 2
    assert evaluation.not_applicable_items == 1
    assert [item.item_id for item in evaluation.evaluations] == [
        "has_income_statement",
        "has_balance_sheet",
        "footnote_crosscheck",
    ]


def test_missing_required_item_result_fails_evaluation() -> None:
    checklist = make_checklist()
    evaluation = evaluate_pdf_validation_checklist(
        checklist,
        [
            make_result(item_id="has_income_statement", status="PASS"),
            make_result(item_id="footnote_crosscheck", status="PASS"),
        ],
    )

    assert evaluation.overall_status is ChecklistEvaluationStatus.FAIL
    assert evaluation.missing_required_item_ids == ["has_balance_sheet"]
    assert evaluation.failing_item_ids == ["has_balance_sheet"]
    assert evaluation.not_assessed_items == 1


def test_advisory_failure_escalates_to_manual_review_without_hard_fail() -> None:
    checklist = make_checklist()
    evaluation = evaluate_pdf_validation_checklist(
        checklist,
        [
            make_result(item_id="has_income_statement", status="PASS"),
            make_result(item_id="has_balance_sheet", status="PASS"),
            make_result(
                item_id="footnote_crosscheck",
                status="FAIL",
                evidence=[{"page_number": 8, "locator_text": "Note 12"}],
            ),
        ],
    )

    assert evaluation.overall_status is ChecklistEvaluationStatus.MANUAL_REVIEW
    assert evaluation.advisory_issue_item_ids == ["footnote_crosscheck"]
    assert evaluation.failing_item_ids == []


def test_evaluate_rejects_duplicate_or_unknown_result_item_ids() -> None:
    checklist = make_checklist()

    with pytest.raises(R11ValidationChecklistError, match="duplicate result item_id: has_income_statement"):
        evaluate_pdf_validation_checklist(
            checklist,
            [
                make_result(item_id="has_income_statement"),
                make_result(item_id="has_income_statement", status="FAIL"),
            ],
        )

    with pytest.raises(R11ValidationChecklistError, match="unexpected result item_id\\(s\\): unknown_item"):
        evaluate_pdf_validation_checklist(
            checklist,
            [make_result(item_id="unknown_item")],
        )


def test_validation_evidence_requires_locator_and_positive_page_number() -> None:
    with pytest.raises(ValidationError, match="validation evidence must include page_number, table_id, or locator_text"):
        PdfValidationEvidence.model_validate({"note": "missing locator"})

    with pytest.raises(ValidationError, match="page_number must be positive"):
        PdfValidationEvidence.model_validate({"page_number": 0, "locator_text": "bad page"})


def test_r11_validation_checklist_tests_do_not_parse_real_pdfs_or_use_network() -> None:
    checklist = make_checklist(
        items=[
            make_checklist_item(level=ChecklistItemLevel.REQUIRED),
        ]
    )
    evaluation = evaluate_pdf_validation_checklist(
        checklist,
        [make_result(status=ChecklistResultStatus.PASS)],
    )

    assert evaluation.checklist_id == "q1_core_pdf_checks"
