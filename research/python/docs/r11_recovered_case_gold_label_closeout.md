# R11.14E Recovered-Case Gold-Label Closeout

## 1. Closeout Decision

R11.14E is complete as a local runtime gold-label validation milestone for newly recovered clean cases.

R11.14E created and validated local runtime gold labels for:

- `WATA.N0000`
- `LDEV.N0000`

Both cases now have local deterministic analysis JSONs, local runtime gold labels, and local validation reports under `.r11_runtime`.

These files are runtime artifacts. They remain ignored and are not committed.

## 2. Why WATA and LDEV Were Promoted

`WATA.N0000` and `LDEV.N0000` were promoted to local runtime gold-label validation because R11.14 recovered both into clean metric cases.

Promotion criteria met by both cases:

- inspection completes
- four expected scorecard metrics are present
- `has_conflicts: false`
- `scorecard.manual_review_required: false`
- missing expected metrics are empty
- deterministic metric values are stable enough for local validation

The goal of this promotion is to add local answer-key coverage for newly recovered non-OCR cases before deciding whether they should become checked-in gold labels later.

## 3. WATA Local Validation Result

Local WATA files:

- analysis JSON: `research/python/.r11_runtime/analysis/wata_q1_2026_analysis.json`
- gold label: `research/python/.r11_runtime/gold_labels/wata_q1_2026_gold_label.json`
- validation report: `research/python/.r11_runtime/gold_labels/wata_q1_2026_gold_label_validation_report.json`

Validation result:

- `overall_result: PASS`
- `passed_count: 13`
- `failed_count: 0`
- `manual_review_count: 0`

Validated checks included:

- statement page `3`
- statement page `5`
- all four expected WATA metrics
- stable scorecard fields including `manual_review_required: false`

Validated WATA metrics:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`
- `group_total_liabilities_growth`

## 4. LDEV Local Validation Result

Local LDEV files:

- analysis JSON: `research/python/.r11_runtime/analysis/ldev_q1_2026_analysis.json`
- gold label: `research/python/.r11_runtime/gold_labels/ldev_q1_2026_gold_label.json`
- validation report: `research/python/.r11_runtime/gold_labels/ldev_q1_2026_gold_label_validation_report.json`

Validation result:

- `overall_result: PASS`
- `passed_count: 15`
- `failed_count: 0`
- `manual_review_count: 0`

Validated checks included:

- statement page `2`
- statement page `4`
- statement page `5`
- statement page `7`
- all four expected LDEV metrics
- stable scorecard fields including `manual_review_required: false`

Validated LDEV metrics:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`
- `group_total_liabilities_growth`

## 5. Updated Local Clean Gold-Label Set

The current local clean gold-label set now includes:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`
- `WATA.N0000`
- `LDEV.N0000`

The first four cases came from the earlier R11.13 gold-label validation foundation. WATA and LDEV were added after R11.14 parser/layout recovery.

## 6. RENU and WIND Manual-Review Boundary

`RENU.N0000` and `WIND.N0000` remain partial manual-review cases.

`RENU.N0000` was partially recovered and now has:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`

It still has:

- `scorecard.manual_review_required: true`
- missing `group_total_liabilities_growth`

`WIND.N0000` was partially recovered and now has:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`

It still has:

- `scorecard.manual_review_required: true`
- missing `group_total_liabilities_growth`

For both RENU and WIND, total liabilities was intentionally not synthesized. They should not be promoted as clean scorecard labels unless a later milestone explicitly approves manual-review labeling, liability synthesis, or a clean explicit total-liabilities source-row recovery.

## 7. GLAS and LALU OCR Deferred Boundary

`GLAS.N0000` and `LALU.N0000` remain deferred OCR cases.

Their failure mode is no usable extractable pypdf text. R11.14 parser/layout hardening and R11.14E local gold-label validation do not add OCR support.

These cases should remain outside deterministic pypdf gold-label promotion until an OCR strategy is planned, approved, and validated.

## 8. Runtime Artifact Boundary

The WATA and LDEV analysis JSONs, local gold labels, and validation reports are runtime artifacts under `.r11_runtime`.

They are intentionally local:

- they are ignored by Git
- they are not staged
- they are not committed
- they are not checked-in production gold labels

Runtime artifacts that must remain uncommitted include:

- local analysis JSONs
- local gold-label JSONs
- local validation reports
- manifests
- PDFs under `.r10_runtime/`
- generated runtime outputs under `.r11_runtime/`

This closeout document is the checked-in record of the local validation milestone. It does not include runtime JSON payloads or local PDF contents.

## 9. What Was Not Gold-Labeled Yet

R11.14E intentionally did not gold-label:

- source-row labels
- expected line-item aliases
- scorecard summary text
- runtime PDF paths

Those fields require manual source-row review before being promoted into checked-in, durable gold-label expectations.

The local gold labels focus on:

- stable statement page classification checks
- expected aggregated metric values
- expected conflict state
- stable scorecard fields
- `manual_review_required`

## 10. Relationship to Future Training and FinQA

The R11.14E artifacts are local answer keys for deterministic validation.

They are not training data yet.

They should not be treated as FinQA-style supervised examples until additional review is complete, especially:

- source-row labels
- source-row spans
- line-item aliases
- statement context
- entity and period scope
- manually verified rationale for each value

Before any checked-in real gold labels or training-oriented datasets are created, row-level manual review is required.

## 11. Recommended Next Phase

Recommended next phase:

- merge this documentation branch
- then choose one of the next validation tracks:
  - add local manual-review gold labels for `RENU.N0000` and `WIND.N0000`
  - design an OCR strategy for `GLAS.N0000` and `LALU.N0000`
  - expand clean local gold labels with more real PDFs

The clean local gold-label set is now large enough to validate recovered parser/layout behavior across six non-OCR cases, while preserving a clear boundary between local runtime validation and checked-in durable gold labels.
