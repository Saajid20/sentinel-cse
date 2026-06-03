# R11 Gold-Label Validation Closeout

## 1. Closeout Decision

R11.13 is complete as the first gold-label validation foundation for Sentinel-CSE R11.

This milestone adds a CSE-specific expected-output design, a safe synthetic checked-in example, a deterministic validator, and local runtime gold labels for the four existing clean-scorecard benchmark cases.

The four local runtime gold-label validations passed:

- `DIMO.N0000`: `PASS`
- `AEL.N0000`: `PASS`
- `SAMP.N0000`: `PASS`
- `COMB.N0000`: `PASS`

This is a gold-label validation foundation, not a declaration that all expected source rows, aliases, or future training labels are complete.

## 2. What R11.13 Added

### R11.13A

Created the gold-label expected output design:

- `research/python/docs/r11_gold_label_expected_output_design.md`

This document defines benchmark levels, proposed case schema fields, expected statement page schema, expected line-item schema, expected metric schema, metric-gap triage categories, current case classification, and the relationship to future FinQA or teaching work.

### R11.13B

Created a checked-in synthetic example:

- `research/python/docs/examples/r11_gold_label_case.example.json`

This fixture uses fake data only. It demonstrates the expected JSON shape without using real CSE values, real PDFs, runtime analysis JSONs, validation reports, manifests, or runtime paths.

### R11.13C

Added a deterministic gold-label validator and CLI:

- `research/python/sentinel_research/agents/r11/validation/gold_label.py`
- `research/python/scripts/r11_validate_gold_label.py`
- `research/python/tests/test_r11_gold_label_validation.py`

Test results:

- `test_r11_gold_label_validation.py`: `9 passed`
- R10/R11 subset: `456 passed, 142 deselected`

The validator compares a gold-label JSON file against an R11 analysis JSON file and emits:

- `overall_result`: `PASS`, `FAIL`, or `MANUAL_REVIEW`
- `passed_count`
- `failed_count`
- `manual_review_count`
- structured checks with `check_id`, `status`, and `message`

### R11.13D

Created and validated local runtime gold labels for the four clean-scorecard cases:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`

These labels and validation reports remain local runtime artifacts under `.r11_runtime/` and must not be committed.

## 3. Why Gold Labels Are Needed Before Teaching or Training

R11 needs CSE-specific gold labels before any FinQA, teaching, training, or fine-tuning work because the model must not learn from ambiguous or incomplete deterministic outputs.

The gold-label layer defines the expected facts R11 should be judged against:

- expected statement pages
- expected metric names
- expected current and previous values
- expected calculated values
- expected scorecard fields
- known gaps and deferred expectations

Without this layer, training or teaching work could accidentally treat missing metrics, weak aliases, entity-scope mistakes, or manual-review gaps as correct behavior.

The deterministic gold-label evaluator should remain the judge. Later LLM or FinQA-aligned work may help with explanation and reasoning, but it should not override deterministic source extraction, value mapping, metric calculation, or validation.

## 4. Local Gold-Label Validation Results

The following real-case gold labels were created locally and validated against existing local R11 analysis JSON files.

### DIMO.N0000

- `overall_result=PASS`
- `passed_count=16`
- `failed_count=0`
- `manual_review_count=0`

Validated local files:

- `research/python/.r11_runtime/gold_labels/dimo_q1_2026_gold_label.json`
- `research/python/.r11_runtime/gold_labels/dimo_q1_2026_gold_label_validation_report.json`

### AEL.N0000

- `overall_result=PASS`
- `passed_count=16`
- `failed_count=0`
- `manual_review_count=0`

Validated local files:

- `research/python/.r11_runtime/gold_labels/ael_q1_2026_gold_label.json`
- `research/python/.r11_runtime/gold_labels/ael_q1_2026_gold_label_validation_report.json`

### SAMP.N0000

- `overall_result=PASS`
- `passed_count=22`
- `failed_count=0`
- `manual_review_count=0`

Validated local files:

- `research/python/.r11_runtime/gold_labels/samp_q1_2026_gold_label.json`
- `research/python/.r11_runtime/gold_labels/samp_q1_2026_gold_label_validation_report.json`

### COMB.N0000

- `overall_result=PASS`
- `passed_count=25`
- `failed_count=0`
- `manual_review_count=0`

Validated local files:

- `research/python/.r11_runtime/gold_labels/comb_q1_2026_gold_label.json`
- `research/python/.r11_runtime/gold_labels/comb_q1_2026_gold_label_validation_report.json`

## 5. What Was Validated

The R11.13D local gold labels validated three layers for the four clean-scorecard cases.

### Statement pages

The labels checked expected statement page classifications:

- income statement pages
- balance sheet / statement of financial position pages
- equity statement pages where present
- cash-flow pages where present

### Aggregated metrics

The labels checked expected aggregated metric names and values using the deterministic validator:

- metric presence
- current value where available
- previous value where available
- calculated value
- conflict expectation
- numeric tolerance

The local labels used the same `0.01` tolerance convention across the four cases.

### Scorecard fields

The labels checked stable scorecard fields:

- `earnings_quality`
- `revenue_trend`
- `margin_trend`
- `balance_sheet_risk`
- `cash_flow_quality`
- `capital_strength`
- `manual_review_required`

All four clean-scorecard cases validated with `manual_review_required=false`.

## 6. What Was Intentionally Not Gold-Labeled Yet

R11.13 intentionally did not gold-label every possible field.

Deferred fields:

- expected line-item aliases
- source-row labels
- row-level source evidence
- scorecard summary text
- `accounting_risk` where absent or not stable
- runtime PDF paths

These omissions are deliberate. Row-level source review should happen before real gold labels are promoted into Git or used as a stronger training/evaluation dataset.

## 7. Runtime Artifact Boundary

The local real-case gold labels and validation reports are runtime artifacts only.

The following remain outside source control:

- `.r11_runtime/`
- local gold-label JSON files
- local gold-label validation reports
- analysis JSON files
- validation manifests
- validation reports
- downloaded PDFs
- runtime PDF paths
- inspection outputs

The checked-in boundary for R11.13 is:

- design documentation
- synthetic example JSON
- deterministic validator code
- validator tests
- closeout documentation

Real local gold labels remain in `.r11_runtime/` until a separate manual review and promotion decision is made.

## 8. Relationship to Existing Benchmarks

R11.13 strengthens the existing validation layers but does not replace them.

### Four-case clean-scorecard benchmark

The four clean-scorecard benchmark cases are:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`

R11.13 adds local gold-label validation over these cases. This turns the clean-scorecard benchmark into a stronger expected-output checkpoint for statement pages, aggregated metrics, and scorecard fields.

### Ten-case statement-level benchmark

The ten-case statement-level benchmark remains distinct:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`
- `RWSL.N0000`
- `REEF.N0000`
- `CITH.N0000`
- `CITW.N0000`
- `ACME.N0000`
- `HVA.N0000`

R11.13 does not promote the six second-wave statement-level cases into clean scorecard cases. Those cases still need metric-gap triage and expected-output design before they can become clean gold-label scorecard fixtures.

## 9. Recommended Next Phase

Recommended next phase:

R11.14 - metric-gap triage and hardening using gold-label failures.

R11.14 should:

- use the gold-label validator to expose precise failures
- review source rows before adding expected line-item aliases
- harden row aliases only after row-level evidence is reviewed
- separate locator gaps, alias gaps, value mapping gaps, entity-scope gaps, duplicate candidates, parse errors, and accepted manual-review cases
- keep real local gold labels out of Git until they are manually reviewed and intentionally promoted

Later FinQA, teaching, training, or fine-tuning work should wait until CSE-specific gold labels mature beyond the current foundation. The next practical step is metric-gap hardening from deterministic gold-label failures, not model training.
