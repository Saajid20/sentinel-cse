# R11 Real PDF Validation Closeout

## 1. Closeout Decision

R11.8B is complete for the current real-PDF validation milestone. The deterministic R11 validation harness and statement-locator refinements have now passed two real CSE banking PDFs using local runtime artifacts:

- `COMB.N0000` Q1 2026
- `SAMP.N0000` Q1 2026

This is a validation closeout, not a production-readiness declaration.

## 2. Validation Result

Latest local manifest result:

- `cases_total`: `2`
- `cases_passed`: `2`
- `cases_failed`: `0`
- `cases_manual_review`: `0`

Per case:

- `COMB`: passed `7` checks
- `SAMP`: passed `12` checks

## 3. Scope Completed

### R11.8A validation harness

Completed:

- checklist foundation
- single deterministic analysis JSON validator
- validation manifest schema/helpers
- multi-case manifest runner
- UTF-8 BOM-tolerant manifest loading

Key scripts/modules:

- `research/python/sentinel_research/agents/r11/validation/checklist.py`
- `research/python/sentinel_research/agents/r11/validation/manifest.py`
- `research/python/scripts/r11_validate_analysis_json.py`
- `research/python/scripts/r11_validate_manifest.py`

### R11.8B real-PDF validation hardening

Completed:

- `R11.8B1`: statement locator support for SAMP-style untitled income-statement pages and cash-flow priority
- `R11.8B2`: resilient per-item metric-build warnings in the manual inspection pipeline so invalid candidates do not abort the run
- `R11.8B3`: equity-statement priority over comprehensive-income markers
- `R11.8B4`: balance-sheet equity-continuation correction so financial-position equity sections do not get misclassified as statement-of-changes-in-equity

## 4. Source Boundary

R10 remains the source boundary.

The second-bank validation used the explicit CSE PDF URL fetch helper on the R10 side before R11 analysis:

- R10 downloads/stores the source PDF locally
- R11 consumes the local R10-sourced PDF path

R11 does not own source downloading for these validations.

## 5. Runtime Artifact Boundary

The following are local runtime artifacts only and must not be committed:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- deterministic analysis JSON files
- validation manifests
- validation reports

This closeout records the validated workflow and outcome, not the runtime files themselves.

## 6. What This Milestone Proved

The deterministic R11 path now has local real-PDF validation coverage across two clean bank financial disclosures with:

- statement classification
- parsed/normalized banking rows
- deterministic metric verification
- aggregation
- scorecard presence
- explicit validation expectations
- multi-case manifest reporting

The SAMP work also showed that the current deterministic path can be hardened incrementally with transparent marker-based rules without widening into OCR, LLM, or network-dependent logic.

## 7. Known Boundaries

This closeout does not prove broad generalization yet across:

- non-bank financial statements
- difficult table-heavy layouts
- scanned or image-heavy PDFs
- OCR-dependent disclosures

Those remain next validation targets.

## 8. Recommended Next Validation Order

1. One non-bank interim statement
2. One difficult or table-heavy text PDF
3. One scanned/image-heavy case only after the deterministic boundary is intentionally widened

## 9. Final Summary

R11.8A and R11.8B together now provide a usable local validation harness plus a two-bank real-PDF deterministic validation checkpoint. The current branch is ready to move from bank-to-bank validation into cross-layout and cross-sector validation, while keeping R10 as the sourcing boundary and keeping runtime artifacts out of Git.
