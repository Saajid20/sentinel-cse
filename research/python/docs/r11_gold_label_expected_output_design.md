# R11 Gold-Label Expected Output Design

## 1. Purpose

R11 needs CSE-specific gold labels before any FinQA, teaching, training, or fine-tuning work.

The current R11 validation foundation proves that deterministic extraction can classify and validate real CSE financial statement pages across a controlled set of PDFs. It does not yet define a durable expected-output dataset. Without explicit expected pages, line items, metrics, scorecard expectations, and failure categories, downstream model work would risk learning from incomplete or ambiguous outputs.

Gold labels should provide the reviewable target that R11 is measured against. They should answer:

- which statement pages are expected
- which labels and aliases are accepted
- which values are required
- which entity and period scopes are required
- which metrics must be calculated
- which gaps are accepted, deferred, or failures
- when manual review is expected rather than a defect

The deterministic gold-label evaluator should become the judge. FinQA or LLM-assisted work can later help with reasoning and explanation, but it should not replace deterministic source extraction, value mapping, or benchmark evaluation.

## 2. Benchmark Levels

Gold-label cases should have one primary benchmark level. A case can also carry known gap categories, but the benchmark level is the headline classification.

### CLEAN_SCORECARD

The case is expected to pass statement classification, line-item extraction, metric calculation, aggregation, and scorecard validation without residual manual-review status.

Use for cases that are suitable as clean regression benchmarks.

### STATEMENT_LEVEL_ONLY

The case is expected to classify required statement pages correctly, but metric extraction and scorecard expectations are not yet complete enough to require a clean scorecard.

Use for cases that validate locator coverage and real-PDF statement detection while metric labels are still being designed.

### HARD_CASE_DEFERRED

The case is known to be useful but intentionally deferred because it requires work outside the current deterministic benchmark boundary or has unresolved evidence quality issues.

Use for cases that should remain in the backlog until the necessary extraction, parsing, or review process exists.

### METRIC_GAP_TRIAGE

The case has extractable statements, but one or more expected metrics are missing, duplicated, conflicted, mapped to the wrong entity scope, or not yet represented in the deterministic metric layer.

Use for inspected cases where the next task is metric-gap diagnosis rather than statement locator hardening.

### OCR_REQUIRED

The case cannot be meaningfully processed through the current pypdf text path because required statement text is absent or not extractable.

Use for scanned, image-heavy, or otherwise OCR-dependent disclosures.

### PARSE_REQUIRED

The case has extractable text, but deterministic parsing fails on malformed, unusual, or currently unsupported financial value formats.

Use for cases where the next work is parser hardening rather than locator or metric mapping.

## 3. Gold-Label Case Schema Proposal

Each gold-label case should be a reviewable JSON object with stable fields. The first implementation should keep the schema explicit and conservative rather than compressing too much meaning into free-form notes.

Proposed top-level fields:

- `schema_version`: version string, for example `r11_gold_label_case_v1`
- `case_id`: stable case identifier, for example `COMB.N0000_2026_Q1`
- `ticker`: CSE ticker, for example `COMB.N0000`
- `company_name`: issuer display name
- `sector_hint`: coarse sector hint used for review and triage, not for overriding extracted evidence
- `source_type`: source category, for example `CSE_REAL_PDF`, `SYNTHETIC_EXAMPLE`, or `LOCAL_REVIEW_ONLY`
- `source_url_or_document_id`: source URL, announcement id, document id, or other stable source reference when allowed
- `local_runtime_pdf_path_optional`: optional local runtime path for reviewer convenience; not required and not suitable for committed real runtime artifacts
- `benchmark_level`: one of the benchmark levels in this document
- `expected_statement_pages`: list of expected statement-page objects
- `expected_line_items`: list of expected line-item objects
- `expected_metrics`: list of expected metric objects
- `expected_scorecard`: optional expected scorecard object or minimal scorecard expectation
- `known_gaps`: list of metric-gap triage categories and explanations
- `manual_review_expected`: boolean indicating whether manual review is an accepted expected outcome
- `notes`: short reviewer notes

Suggested JSON shape:

```json
{
  "schema_version": "r11_gold_label_case_v1",
  "case_id": "SYNTH.N0000_2026_Q1",
  "ticker": "SYNTH.N0000",
  "company_name": "Synthetic Example PLC",
  "sector_hint": "synthetic",
  "source_type": "SYNTHETIC_EXAMPLE",
  "source_url_or_document_id": "synthetic-example",
  "local_runtime_pdf_path_optional": null,
  "benchmark_level": "CLEAN_SCORECARD",
  "expected_statement_pages": [],
  "expected_line_items": [],
  "expected_metrics": [],
  "expected_scorecard": null,
  "known_gaps": [],
  "manual_review_expected": false,
  "notes": "Small fake case for schema and validator development."
}
```

## 4. Expected Statement Page Schema

Expected statement pages define what the locator must classify.

Fields:

- `page_number`: one-based page number in the extracted PDF
- `statement_type`: expected statement type, for example `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `EQUITY_STATEMENT`, or `NOTES`
- `confidence_requirement`: minimum accepted locator confidence, for example `HIGH`, `MEDIUM`, or `LOW`
- `required_markers`: markers that must be present in the matched marker list or page evidence
- `optional_markers`: useful markers that may appear but are not required
- `accepted_aliases`: accepted title or row-label variants for this statement page

Suggested JSON shape:

```json
{
  "page_number": 3,
  "statement_type": "INCOME_STATEMENT",
  "confidence_requirement": "HIGH",
  "required_markers": ["STATEMENT OF PROFIT OR LOSS"],
  "optional_markers": ["REVENUE", "PROFIT FOR THE PERIOD"],
  "accepted_aliases": [
    "Statement of Profit or Loss",
    "Statement of Comprehensive Income",
    "Income Statement"
  ]
}
```

Statement page labels should preserve the distinction between expected evidence and classifier behavior. A marker can be accepted without requiring the locator to use that exact marker as its only reason.

## 5. Expected Line-Item Schema

Expected line items define the source values that should be found before metrics are calculated.

Fields:

- `statement_type`: statement where the line item is expected
- `page_number`: expected source page
- `canonical_item`: deterministic canonical item name, for example `revenue` or `profit_for_the_period`
- `label_aliases`: accepted source labels
- `entity_scope`: expected entity scope, for example `group`, `company`, `bank`, or `consolidated`
- `period_scope`: expected period scope, for example `current_quarter`, `previous_quarter`, `current_year_to_date`, or `previous_year_to_date`
- `expected_current_value`: expected current value
- `expected_previous_value`: expected comparison value
- `unit`: value unit, for example `LKR`, `LKR_THOUSANDS`, or `PERCENT`
- `tolerance`: accepted numeric tolerance
- `extraction_required`: boolean indicating whether missing extraction is a validation failure

Suggested JSON shape:

```json
{
  "statement_type": "INCOME_STATEMENT",
  "page_number": 3,
  "canonical_item": "revenue",
  "label_aliases": ["Revenue", "Revenue from contracts with customers"],
  "entity_scope": "group",
  "period_scope": "current_year_to_date",
  "expected_current_value": 1000000,
  "expected_previous_value": 900000,
  "unit": "LKR",
  "tolerance": 1,
  "extraction_required": true
}
```

Line-item labels should be explicit enough to support alias hardening. If a case fails because `Revenue from contracts with customers` does not map to `revenue`, that is a `LINE_ITEM_ALIAS_GAP`, not a generic validation failure.

## 6. Expected Metric Schema

Expected metrics define calculated or reported financial measures after line items have been extracted and mapped.

Fields:

- `metric_name`: deterministic metric name, for example `group_revenue_yoy_growth`
- `source_canonical_item`: source canonical item used by the metric
- `entity_scope`: expected entity scope
- `current_value`: expected source current value
- `previous_value`: expected source previous value
- `calculated_value`: expected deterministic calculation result
- `reported_value_optional`: optional reported value from the PDF, when the issuer reports the metric directly
- `tolerance`: accepted numeric tolerance
- `conflict_expected`: boolean indicating whether a known source conflict is expected and should be handled deliberately
- `manual_review_if_missing`: boolean indicating whether missing this metric should trigger manual review rather than hard failure

Suggested JSON shape:

```json
{
  "metric_name": "group_revenue_yoy_growth",
  "source_canonical_item": "revenue",
  "entity_scope": "group",
  "current_value": 1000000,
  "previous_value": 900000,
  "calculated_value": 0.111111,
  "reported_value_optional": null,
  "tolerance": 0.0001,
  "conflict_expected": false,
  "manual_review_if_missing": true
}
```

Metric expectations should evaluate deterministic calculations and source-value selection separately. A case can have correct arithmetic but wrong source scope, or correct source mapping but a missing scorecard expectation.

## 7. Metric-Gap Triage Categories

Gold-label validation should report precise gap categories. These categories should be attached to failed expectations and known deferred cases.

### LOCATOR_GAP

Required statement pages are present in extractable text, but the statement locator does not classify them correctly.

Typical fix layer: statement locator markers or priority rules.

### LINE_ITEM_ALIAS_GAP

The expected row exists, but the label is not mapped to the intended canonical item.

Typical fix layer: row canonicalization or alias mapping.

### VALUE_MAPPING_GAP

The expected row maps to a canonical item, but the wrong numeric column, period, or value is selected.

Typical fix layer: value mapper or table/column interpretation.

### PARSE_ERROR

The extracted text contains a value that the parser cannot normalize or validates as malformed.

Typical fix layer: numeric parser or extraction normalization.

### OCR_NEEDED

The required statement text is not available to pypdf and requires OCR or a widened extraction path.

Typical fix layer: OCR planning and source extraction boundary design.

### ENTITY_SCOPE_GAP

The extracted value uses the wrong entity scope, such as company instead of group.

Typical fix layer: entity-scope detection and candidate ranking.

### DUPLICATE_CANDIDATE_GAP

Multiple candidates for the same metric compete and the deterministic layer cannot choose the intended one without conflict or manual review.

Typical fix layer: candidate ranking, source preference, or conflict handling.

### SCORECARD_EXPECTATION_GAP

The metric extraction may be acceptable, but the expected scorecard outcome is missing, ambiguous, or not yet defined.

Typical fix layer: scorecard expectation design rather than extraction.

### ACCEPTED_MANUAL_REVIEW

Manual review is an expected, accepted result for this case under the current benchmark level.

Typical use: hard/deferred cases, incomplete metric expectations, or intentionally unresolved edge cases.

## 8. Current Case Classification

Current known cases should be classified as follows for the initial R11.13 design layer.

### CLEAN_SCORECARD

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`

These are the current clean scorecard benchmark cases.

### STATEMENT_LEVEL_ONLY with METRIC_GAP_TRIAGE

- `RWSL.N0000`
- `REEF.N0000`
- `CITH.N0000`
- `CITW.N0000`
- `ACME.N0000`
- `HVA.N0000`

These cases are validated at the statement-classification level. They should not yet be described as clean scorecard cases. Their next use is metric-gap triage and expected-output design.

### OCR_REQUIRED

- `GLAS.N0000`: no extractable pypdf text
- `LALU.N0000`: no extractable pypdf text

These cases should stay outside deterministic pypdf-only validation until OCR support is intentionally designed.

### PARSE_REQUIRED

- `WATA.N0000`: malformed extracted financial value
- `RENU.N0000`: malformed extracted financial value

These cases should drive parser hardening only after the expected value formats and failure rules are documented.

### METRIC_GAP_TRIAGE or ACCEPTED_MANUAL_REVIEW

- `LDEV.N0000`: inspected, but current evidence points to a manual-review scorecard gap
- `WIND.N0000`: inspected, but current evidence points to weak metric extraction and manual-review scorecard gap

Until exact expected line items and metrics are defined, these should be treated as `METRIC_GAP_TRIAGE` cases with `ACCEPTED_MANUAL_REVIEW` available as an expected outcome.

## 9. Relationship to FinQA and Teaching

FinQA should not be used to directly train Sentinel-CSE yet.

R11 first needs CSE-specific gold labels because CSE interim financial statements have issuer-specific layouts, group/company scope patterns, period columns, local row labels, and disclosure conventions that generic financial QA datasets do not fully encode.

FinQA can become useful later for:

- testing financial reasoning patterns
- evaluating explanation quality
- comparing arithmetic reasoning strategies
- designing question-answer tasks over already verified CSE facts

But FinQA should not override the deterministic source boundary. The deterministic extractor, mapper, calculator, and gold-label evaluator should remain the judge for CSE source truth.

The intended relationship is:

- CSE gold labels define expected source facts and metrics
- deterministic validation decides pass, fail, and gap category
- LLM or FinQA-aligned work helps explain verified facts or reason over verified metrics
- model output never replaces source extraction or gold-label validation

This keeps training and teaching work downstream of evidence quality rather than letting generated explanations mask extraction defects.

## 10. Recommended Next Phase

Recommended next sequence:

### R11.13B

Create a checked-in example gold-label JSON file with one small synthetic or fake case.

The example should use invented values and no real PDF artifact. Its purpose is schema review and validator design, not benchmark scoring.

### R11.13C

Implement a gold-label validator against existing analysis JSON.

The validator should compare expected statement pages, expected line items, expected metrics, scorecard expectations, and known gaps. It should report precise triage categories rather than generic pass/fail output.

### R11.13D

Manually create local runtime gold labels for:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`

These labels can be local runtime artifacts first. They should be reviewed before any real-case labels are promoted into source control.

### R11.14

Begin metric-gap hardening using gold-label failures.

R11.14 should use the validator output to choose focused fixes in the correct layer: locator, alias mapping, value mapping, entity scope, duplicate candidate handling, parser normalization, or scorecard expectation design.

The immediate priority is not training. It is to make failures explicit, reviewable, and attached to the correct deterministic layer.
