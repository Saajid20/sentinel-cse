# R11 PDF Validation Checklist Foundation

R11.8A1 starts with a narrow deterministic foundation for PDF validation checklists. This is intentionally not a runner and does not read PDFs.

## Scope

The module lives under `research/python/sentinel_research/agents/r11/validation/` and provides:

- `PdfValidationChecklistItem`: one checklist definition with `REQUIRED` or `ADVISORY` severity.
- `PdfValidationChecklist`: ordered checklist definition with unique item ids.
- `PdfValidationChecklistResult`: one supplied validation outcome with optional evidence pointers.
- `PdfValidationEvidence`: deterministic page/table/text locator metadata only.
- `evaluate_pdf_validation_checklist(...)`: pure result evaluation with no file IO.

## Evaluation Rules

- Missing `REQUIRED` items fail the overall evaluation.
- `REQUIRED` items marked `FAIL` or `NOT_APPLICABLE` fail the overall evaluation.
- `REQUIRED` items marked `MANUAL_REVIEW` escalate the overall evaluation to `MANUAL_REVIEW` unless a hard fail already exists.
- `ADVISORY` items marked `FAIL` or `MANUAL_REVIEW` escalate the overall evaluation to `MANUAL_REVIEW` but do not hard-fail the checklist.
- Evaluation order follows checklist order, not input result order.

## Non-Goals

- No PDF parsing.
- No OCR.
- No network calls.
- No runtime fixture directories.
- No coupling to R10 runtime paths or live systems.

This foundation is meant to be fed later by deterministic extractors or fake harness inputs, while keeping the checklist semantics testable in isolation.
