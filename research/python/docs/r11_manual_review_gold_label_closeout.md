# R11.14F3 Manual-Review Gold-Label Closeout

## 1. Closeout Decision

R11.14F3 is complete as a documentation closeout for local runtime manual-review gold labels.

R11.14F created and validated local runtime manual-review gold labels for the two partially recovered real PDF cases:

- `RENU.N0000`
- `WIND.N0000`

Both cases now have local deterministic analysis outputs, local runtime gold labels, and local validation reports under `.r11_runtime`.

Both validations reached the expected `MANUAL_REVIEW` result with zero failures. The manual-review state is intentional and reflects a known missing metric boundary, not a validator failure.

## 2. Why RENU and WIND Are Manual-Review Cases

`RENU.N0000` and `WIND.N0000` are manual-review gold-label cases, not clean scorecard cases, because each is still missing:

- `group_total_liabilities_growth`

Both cases have three recovered, validated passing metrics:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`

They are not clean cases because the scorecard still requires manual review when expected key metrics are missing. In both cases, total liabilities was intentionally not synthesized from component rows or balance-sheet arithmetic.

The clean-case boundary remains:

- all expected scorecard metrics present
- no conflicts
- `manual_review_required: false`

RENU and WIND do not meet that boundary because `manual_review_required: true` is the expected result.

## 3. RENU Validation Result

Local RENU files:

- analysis JSON: `research/python/.r11_runtime/analysis/renu_q1_2026_analysis.json`
- gold label: `research/python/.r11_runtime/gold_labels/renu_q1_2026_manual_review_gold_label.json`
- validation report: `research/python/.r11_runtime/gold_labels/renu_q1_2026_manual_review_gold_label_validation_report.json`

Validation result:

- `overall_result: MANUAL_REVIEW`
- `passed_count: 11`
- `failed_count: 0`
- `manual_review_count: 1`

Expected manual-review reason:

- `manual_review_required: true`
- `group_total_liabilities_growth` is missing
- total liabilities was intentionally not synthesized

Recovered passing metrics:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`

## 4. WIND Validation Result

Local WIND files:

- analysis JSON: `research/python/.r11_runtime/analysis/wind_q1_2026_analysis.json`
- gold label: `research/python/.r11_runtime/gold_labels/wind_q1_2026_manual_review_gold_label.json`
- validation report: `research/python/.r11_runtime/gold_labels/wind_q1_2026_manual_review_gold_label_validation_report.json`

Validation result:

- `overall_result: MANUAL_REVIEW`
- `passed_count: 12`
- `failed_count: 0`
- `manual_review_count: 1`

Expected manual-review reason:

- `manual_review_required: true`
- `group_total_liabilities_growth` is missing
- total liabilities was intentionally not synthesized

Recovered passing metrics:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_equity_growth`

## 5. Known Missing Metric Boundary

The known missing metric boundary for both RENU and WIND is:

- `group_total_liabilities_growth` is missing
- no clean explicit total-liabilities source row was promoted into the recovered metric set
- total liabilities was intentionally not synthesized

This boundary is important because liability synthesis would introduce an additional policy decision and arithmetic derivation beyond the approved partial-recovery scope.

The current R11.14F rule is:

- validate explicit recovered metrics
- mark expected manual-review cases as `MANUAL_REVIEW`
- do not hallucinate, infer, or synthesize missing values to force a clean `PASS`

## 6. Updated Local Gold-Label Matrix

Current local clean scorecard cases:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`
- `WATA.N0000`
- `LDEV.N0000`

Current local manual-review scorecard cases:

- `RENU.N0000`
- `WIND.N0000`

Current OCR deferred cases:

- `GLAS.N0000`
- `LALU.N0000`

The clean cases validate expected full-scorecard `PASS` behavior. The manual-review cases validate expected partial-scorecard `MANUAL_REVIEW` behavior. GLAS and LALU remain outside deterministic pypdf gold-label validation until an OCR strategy is designed and approved.

## 7. Runtime Artifact Boundary

The local R11.14F analysis JSONs, gold labels, and validation reports stay under:

- `research/python/.r11_runtime/`

They are runtime artifacts:

- they are not committed
- they are not staged
- they are not checked-in durable gold labels
- they do not include promoted source-row evidence yet

Runtime artifacts that remain uncommitted include:

- local analysis JSONs
- local gold-label JSONs
- local validation reports
- manifests
- PDFs under `.r10_runtime/`
- generated outputs under `.r11_runtime/`
- `.pytest_tmp_*` folders

This closeout document is the checked-in record of the R11.14F manual-review gold-label milestone. It does not include runtime JSON payloads or local PDF contents.

## 8. What Was Intentionally Not Changed

R11.14F3 is documentation only.

The following were intentionally not changed:

- parser code
- validator code
- tests
- R10 ingestion, lookup, fetch, or runtime code
- OCR code or OCR provider integration
- LLM, DeepSeek, or other provider logic
- network access behavior
- ATrad code
- pipeline code
- strategy code
- broker code
- session code
- execution code
- order code
- live-engine code

No dependencies were added.

## 9. Why This Matters

The R11 gold-label validator now supports both:

- clean `PASS` cases for complete recovered scorecards
- expected `MANUAL_REVIEW` cases for partial real PDF recoveries

This lets R11 validate partial recoveries without pretending missing source evidence exists.

For RENU and WIND, the validator confirms the recovered metrics and scorecard fields while preserving the missing-liabilities boundary. That gives the project useful regression coverage for real PDF recovery work without hallucinating or synthesizing unavailable values.

## 10. Recommended Next Phase Options

Recommended next phase options:

- expand clean local gold labels beyond the current six cases
- design an OCR strategy for `GLAS.N0000` and `LALU.N0000`
- design generic table/block reconstruction after collecting more examples

Any future promotion of RENU or WIND from manual-review to clean should require either a clean explicit total-liabilities source-row recovery or an explicitly approved liability-synthesis policy.
