# R11 Non-Bank Metric Conflict Closeout

## 1. Closeout Decision

R11.9B is complete as a documentation-only closeout for the first non-bank metric-conflict investigation and correction.

This is a successful fix closeout for the AEL non-bank baseline issue, not a broad declaration that all non-bank layouts are now fully covered. The original manual-review result was caused by false upstream metric candidates, and the implemented fix removed those false candidates without weakening deterministic aggregation behavior.

## 2. Original AEL Baseline Problem

R11.9A established the first non-bank baseline using:

- company: `Access Engineering PLC`
- ticker: `AEL.N0000`
- report focus range: pages `2-6`

The baseline passed statement validation and produced a scorecard, but the scorecard required manual review because:

- aggregated metric conflicts detected: `group_profit_for_the_period_yoy_growth`

Original conflicting outcome:

- `group_profit_for_the_period_yoy_growth`
- `occurrence_count = 3`
- `conflict = true`
- `scorecard.manual_review_required = true`

## 3. Diagnosis Summary

R11.9B1 established that the problem was not in scorecard logic and not in aggregator strictness.

Root cause summary:

- upstream COMB-style six-column assumptions were being applied too broadly to a non-bank income-statement layout
- a repeated four-value `Profit for the period` row was interpreted as if it contained reported percent columns
- that caused a large currency amount to be treated as `group_reported_change_percent`
- a likely standalone/company income-statement page also produced `group_*` metric candidates even though a clearer group/consolidated income-statement page was present

Interpretation:

- the bad result came from false candidate creation
- the conflict itself was real under the then-current input set
- the correct place to fix the issue was candidate selection and value mapping before aggregation

## 4. Fix Summary

R11.9B2 implemented the smallest safe upstream correction.

Changes made:

- four-value rows now map as dual-scope current/previous rows rather than fake percent-bearing rows
- group metric generation now prefers income-statement tables with group/consolidated markers when multiple income-statement pages are present
- example markers include `Non-controlling interest`, `Equity holders of the parent`, and `Attributable to equity holders`
- same-table duplicate candidates repeating the same current/previous pair without a reported percent are pruned when a richer candidate already exists

Effect on AEL:

- the repeated subtotal-style `Profit for the period` row no longer injects a bogus reported percent
- the likely standalone/company income-statement page no longer contributes `group_*` metric candidates when a clearer group-marked page is available
- only the valid primary group candidate remains for `group_profit_for_the_period_yoy_growth`

## 5. What Was Intentionally Not Changed

The following were intentionally left unchanged:

- `metric_builder.py`
- `metric_aggregator.py`
- scorecard logic
- aggregator conflict semantics
- deterministic validation boundary

No change was made to:

- silently coerce missing or invalid values to zero
- suppress conflicts globally
- relax manual-review behavior for genuine conflicts

The fix was deliberately constrained to upstream candidate mapping and selection.

## 6. Validation Result After Fix

Post-fix AEL result:

- `group_profit_for_the_period_yoy_growth`
- `occurrence_count = 1`
- `conflict = false`
- `scorecard.manual_review_required = false`

Validation summary:

- AEL analysis JSON validation: `PASS`
- scorecard: present
- manual review count: `0`

Focused regression coverage:

- `test_r11_value_mapper.py`: `14 passed`
- `test_r11_inspect_pypdf_baseline.py`: `12 passed`
- R10/R11 subset: `432 passed`, `111 deselected`

What this proves:

- the first non-bank baseline issue was a false-candidate problem, not a downstream scoring problem
- the deterministic path can be corrected incrementally for non-bank layouts while preserving strict aggregation behavior
- AEL now serves as a clean corrected non-bank validation case within the current deterministic boundary

## 7. Remaining Limitations

Current limitations remain:

- this closeout is based on one non-bank company family and one resolved conflict pattern
- the group/company distinction is still marker-driven, not a general semantic layout model
- non-bank disclosures with different attribution wording or less explicit scope markers may still require additional hardening
- other repeated-row or subtotal patterns may appear in future issuers
- this does not prove universal non-bank coverage across all CSE sectors or report formats

## 8. Recommended Next Phase

Recommended next phase:

- expand non-bank deterministic validation to additional issuers and layouts

Priority order:

1. Validate one more non-bank interim report with clear consolidated/standalone separation
2. Validate one non-bank case with weaker or alternative attribution wording
3. Inspect whether similar four-value repeated-row patterns appear in balance-sheet or equity-derived metric paths
4. Only widen logic further if a second or third non-bank case shows a stable repeatable pattern

The next phase should continue to preserve:

- strict deterministic aggregation
- no OCR/LLM/network dependency
- R10 as the sourcing boundary

## 9. Runtime Artifact Boundary

This closeout does not add or preserve runtime artifacts in Git.

The following remain local runtime artifacts only and must not be committed:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- analysis JSON files
- validation reports
- scorecards
- other local outputs produced during manual inspection or validation

This document records the problem, diagnosis, fix boundary, and validated outcome only. It does not promote runtime artifacts into source control.
