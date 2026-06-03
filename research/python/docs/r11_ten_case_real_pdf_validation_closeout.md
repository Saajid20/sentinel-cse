# R11 Ten-Case Real PDF Validation Closeout

## 1. Closeout Decision

R11.12 is complete as a documentation closeout for the ten-case real CSE PDF statement-level validation milestone.

The ten-case statement-level validation manifest passed:

- `cases_total: 10`
- `cases_passed: 10`
- `cases_failed: 0`

This is a ten-case statement-level benchmark. It is not a ten-case clean scorecard benchmark.

R11.12 expands the real-PDF validation foundation from the existing four-case clean scorecard benchmark to a broader ten-case statement-classification checkpoint. The result is meaningful because it shows that the deterministic pypdf path can identify required financial statement pages across more real CSE reporting styles, but it does not remove the need for expected-output design, metric-gap triage, OCR planning, or future gold-label work.

## 2. Validation Layers

R11 now has two separate validation layers that should not be conflated.

### Four-case clean scorecard benchmark

The existing clean scorecard benchmark remains:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`

Interpretation:

- statement pages classify correctly
- deterministic metric extraction is clean enough for the expected validation checks
- aggregation and scorecard generation complete without residual manual-review status in the benchmark
- this layer is the current clean scorecard regression baseline

### Ten-case statement-level benchmark

The R11.12 ten-case benchmark includes the four clean cases plus six second-wave statement-level cases:

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

Interpretation:

- required statement pages classify correctly across all ten cases
- second-wave cases are statement-level validation cases, not clean scorecard cases
- some second-wave layouts still need explicit expected metrics and metric-gap triage before they can become clean scorecard benchmark cases

The correct summary is:

R11.12 establishes a ten-case real-PDF statement-level benchmark and preserves the four-case clean scorecard benchmark.

## 3. Cases Included in the Ten-Case Benchmark

The ten-case statement-level benchmark consists of:

- `COMB.N0000`: clean scorecard benchmark case
- `SAMP.N0000`: clean scorecard benchmark case
- `AEL.N0000`: clean scorecard benchmark case
- `DIMO.N0000`: clean scorecard benchmark case
- `RWSL.N0000`: second-wave statement-level case
- `REEF.N0000`: second-wave statement-level case
- `CITH.N0000`: second-wave statement-level case
- `CITW.N0000`: second-wave statement-level case
- `ACME.N0000`: second-wave statement-level case
- `HVA.N0000`: second-wave statement-level case

The combined set gives R11 broader real-CSE coverage across banks, engineering/construction, hotels/leisure, food, packaging, and manufacturing-style reports. This is useful validation diversity, but it is still a small controlled benchmark rather than broad sector generalization.

## 4. Batch Helper Summary

R11.12 added a controlled batch real-PDF baseline helper:

- `research/python/scripts/r11_batch_real_pdf_baseline.py`

It also added an example candidate config:

- `research/python/docs/examples/r11_ten_case_candidate_config.example.json`

And focused tests:

- `research/python/tests/test_r11_batch_real_pdf_baseline.py`

The batch helper supports controlled real-PDF candidate runs by:

- looking up candidate disclosures
- selecting and fetching configured real PDF reports
- running deterministic pypdf inspection
- validating statement-level expectations
- recording per-case outcomes
- continuing across hard failures instead of aborting the whole batch

The per-case resilience is important. It lets the benchmark distinguish successful statement-level cases from OCR-needed cases, parse errors, and metric-quality gaps without losing the full batch result.

## 5. First-Wave Hard and Deferred Cases

The first expansion wave produced several useful hard/deferred cases. These are not part of the ten passing statement-level benchmark, but they define important future work.

- `GLAS.N0000`: `OCR_NEEDED`; no extractable pypdf text
- `LALU.N0000`: `OCR_NEEDED`; no extractable pypdf text
- `WATA.N0000`: `PARSE_ERROR`; malformed extracted financial value
- `RENU.N0000`: `PARSE_ERROR`; malformed extracted financial value
- `LDEV.N0000`: inspected, but scorecard had a manual-review gap
- `WIND.N0000`: inspected, but metric extraction was weak and scorecard required manual review

These cases should remain hard/deferred examples until the next phase defines expected line items, expected metrics, and failure categories clearly enough to make their outcomes actionable.

## 6. Second-Wave Statement-Level Successes

The second-wave cases inspected successfully at the statement-classification level:

- `RWSL.N0000`
- `REEF.N0000`
- `CITH.N0000`
- `CITW.N0000`
- `ACME.N0000`
- `HVA.N0000`

Two observed locator gaps were closed with transparent marker-based rules:

- `RWSL.N0000`: `STATEMENT OF PROFIT OR LOSS` now classifies page 3 as `INCOME_STATEMENT`
- `HVA.N0000`: `Statement of Cashflow` and `Cash Flow From Operating Activities` now classify page 6 as `CASH_FLOW`

The statement locator was hardened for:

- `STATEMENT OF PROFIT OR LOSS`
- `STATEMENT OF CASHFLOW`
- `CASH FLOW FROM OPERATING ACTIVITIES`

The locator remains deterministic and marker-based. It does not use LLMs, OCR, or real-PDF parsing inside tests.

## 7. What This Proves

R11.12 proves:

- R11 can classify required statement pages across ten real CSE PDFs
- the deterministic pypdf path works across a broader controlled set of real report layouts
- marker-based locator hardening can close observed statement-classification gaps without widening the system boundary
- the batch helper can look up, fetch, inspect, and validate controlled real-PDF candidates
- the batch helper is resilient per case and records hard failures instead of aborting the full batch
- R11 now has a repeatable ten-case statement-level benchmark that can be used as a regression checkpoint

The milestone is strongest as evidence of statement-page classification robustness under controlled real-PDF conditions.

## 8. What This Does Not Prove

R11.12 does not prove:

- broad sector generalization across the full CSE universe
- OCR or scanned-PDF support
- that all ten cases have clean scorecards
- full metric extraction quality across all non-bank layouts
- complete handling of malformed numeric values
- complete handling of weak, sparse, or irregular table extraction
- readiness for training, fine-tuning, or teaching from generated outputs

The ten-case result should therefore be described as statement-level validation, not as production readiness and not as full metric-quality validation.

## 9. Runtime Artifact Boundary

This closeout records the validation result and interpretation only. It does not promote runtime artifacts into source control.

The following remain runtime-only and must not be committed:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- analysis JSON files
- validation reports
- validation manifests
- runtime candidate manifests
- scorecard outputs
- inspection dumps
- other local generated artifacts

The source-controlled boundary for R11.12 is code, tests, example configuration, and documentation. Real PDFs and generated runtime outputs remain local artifacts.

## 10. Recommended Next Phase

Recommended next phase:

R11.13 - gold-label expected output design and metric-gap triage.

R11.13 should define:

- expected statement pages per case
- expected line items per case
- expected metrics per case
- acceptable aliases and row-label variants
- group/company selection expectations
- current-period and prior-period value expectations
- failure categories for OCR-needed cases, parse errors, weak extraction, missing metrics, duplicate candidates, and manual-review scorecard gaps
- promotion criteria for moving a statement-level case into the clean scorecard benchmark

This should happen before any training or fine-tuning work. The immediate need is a stronger expected-output design, not model teaching.

## 11. Relationship to Future Teaching, FinQA, and Gold-Label Work

R11.12 is a useful foundation for future teaching, FinQA-style supervision, and gold-label dataset work, but it is not itself a training-ready dataset.

What R11.12 contributes:

- a ten-case real-PDF statement-level benchmark
- a four-case clean scorecard benchmark that remains distinct
- second-wave examples with known statement-level success and known metric-quality gaps
- hard/deferred cases that can seed failure-category design
- a batch helper that can rerun controlled candidates and record per-case outcomes

What must happen before teaching or fine-tuning:

- define expected line items and metrics explicitly
- classify failure modes consistently
- separate OCR failures from parser failures and metric-quality failures
- identify which cases are gold-label clean, which are statement-only, and which are hard/deferred
- validate that labels are stable and reviewable by humans

The right next step is R11.13 gold-label expected output design and metric-gap triage. Training or FinQA-aligned teaching should wait until the benchmark has explicit labels, clear failure categories, and a larger set of clean expected outputs.
