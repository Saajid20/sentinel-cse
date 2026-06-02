# R11 Second Non-Bank Validation Closeout

## 1. Closeout Decision

R11.10 is complete as a documentation-only closeout for the second non-bank validation case.

This is a successful second non-bank validation checkpoint, not a declaration that all non-bank layouts are now fully generalized. The DIMO case initially exposed a deterministic canonicalization gap, and the resulting fix closed that gap without weakening the rest of the R11 deterministic path.

## 2. Why DIMO Was Selected

`DIMO.N0000 / Diesel & Motor Engineering PLC` was selected as the second non-bank validation case because:

- R11.9A/B had already covered and fixed one non-bank baseline using `AEL.N0000`
- a second issuer was needed to test whether the deterministic path held across a different non-bank layout and wording style
- DIMO presented a useful validation shape with the expected core financial statements across pages `2-6`
- DIMO also introduced a meaningful label variation in the income statement:
  `Profit/(loss) for the period`

That made DIMO a good follow-on case for testing whether the non-bank path had really generalized beyond the first issuer.

## 3. R10 Sourcing Path

R10 remained the source boundary for this validation.

The source path was:

1. R10 financial reports discovery identified the DIMO report source.
2. R10 then used the explicit PDF URL ingestion path to obtain the report locally.
3. R11 consumed the resulting local R10-sourced PDF.

R11 did not perform report discovery or PDF downloading for this validation.

## 4. DIMO Statement Validation Result

Case:

- `DIMO.N0000`
- `Diesel & Motor Engineering PLC`

Statement classifications:

- page `2`: `INCOME_STATEMENT` `HIGH`
- page `3`: `INCOME_STATEMENT` `HIGH`
- page `4`: `BALANCE_SHEET` `HIGH`
- page `5`: `EQUITY_STATEMENT` `HIGH`
- page `6`: `CASH_FLOW` `HIGH`

What passed immediately:

- statement classification passed across the focused page range
- validation produced a scorecard
- analysis JSON validation passed

This confirmed that the second non-bank report still fit the current deterministic statement-location and page-classification boundary.

## 5. Initial Metric Gap

The initial DIMO result was not a clean fully automatic validation result.

Initial outcome:

- validation: `PASS`
- scorecard: present
- total verified metric count: `3`
- `scorecard.manual_review_required = true`

The missing key metric was:

- `group_profit_for_the_period_yoy_growth`

Initial scorecard consequence:

- `missing_expected_metrics` included `group_profit_for_the_period_yoy_growth`
- `metric_names_used` included only:
  - `group_total_assets_growth`
  - `group_total_liabilities_growth`
  - `group_total_equity_growth`

## 6. Diagnosis

The DIMO issue was not caused by value mapping, aggregation, scorecard logic, or metric candidate filtering.

Root cause:

- DIMO used the label `Profit/(loss) for the period`
- label normalization converted that into `profit loss for the period`
- canonicalization then fell back to `profit_loss_for_the_period`
- `metric_builder.py` supports `profit_for_the_period`, not `profit_loss_for_the_period`
- as a result, the income-statement profit row was treated as unsupported and no `group_profit_for_the_period_yoy_growth` metric was emitted

Interpretation:

- the issue was a line-item normalization / canonicalization gap
- the income-statement row values themselves were valid and already mapped correctly
- the scorecard was correctly reporting the missing metric rather than mis-scoring the case

## 7. Fix Summary

R11.10B applied the smallest safe fix at the line-item canonicalization boundary.

Alias support was added so normalized `Profit/(loss)` variants map to the existing deterministic canonicals:

- `profit loss for the period`
- `profit loss for the year`
- `profit loss for the quarter`
  -> `profit_for_the_period`

And likely before-tax variants now map to the existing before-tax canonical:

- `profit loss before tax`
- `profit loss before income tax`
  -> `profit_before_income_tax`

Effect:

- the DIMO income-statement profit row now reaches metric generation under an already-supported canonical
- `group_profit_for_the_period_yoy_growth` can be emitted without changing downstream logic

## 8. What Was Intentionally Not Changed

The following were intentionally left unchanged:

- `metric_builder.py`
- `metric_aggregator.py`
- scorecard code
- `value_mapper.py`
- deterministic aggregation behavior

No change was made to:

- relax strict metric-building rules
- suppress scorecard manual review globally
- change conflict semantics
- add OCR, LLM, or network-dependent logic

The fix was deliberately constrained to line-item aliasing.

## 9. Post-Fix Validation Result

After the alias fix, DIMO now emits:

- `group_profit_for_the_period_yoy_growth`

Post-fix profit-metric result:

- `occurrence_count = 1`
- `conflict = false`

Post-fix scorecard result:

- `scorecard.manual_review_required = false`
- `missing_expected_metrics = []`

Validation result:

- DIMO validation command returned `overall result: PASS`
- scorecard remained present
- manual review count became `0`

Regression coverage:

- `test_r11_line_item_mapper.py`: `16 passed`
- R10/R11 subset: `435 passed`, `111 deselected`

What this proves:

- the second non-bank case exposed a deterministic label-variant gap rather than a broader architectural problem
- the deterministic path can be hardened incrementally through canonicalization improvements
- a second non-bank issuer now validates cleanly within the current R11 boundary

## 10. Remaining Limitations

Current limitations remain:

- only two non-bank issuers have been validated so far
- non-bank label variation is still handled through explicit deterministic alias coverage rather than a broader semantic normalization model
- future issuers may introduce other wording variants beyond the current `Profit/(loss)` family
- this milestone does not prove universal generalization across all non-bank CSE reporting styles

## 11. Recommended Next Phase

Recommended next phase:

- continue non-bank deterministic validation across additional issuers and layout variants

Priority focus:

1. Validate another non-bank issuer with different profit/loss wording or statement typography.
2. Validate a case with weaker consolidated/standalone cues.
3. Inspect whether other slash-style label variants should be normalized into existing canonical names.
4. Continue preserving strict deterministic aggregation and scorecard behavior while expanding issuer coverage.

The next phase should keep:

- R10 as the sourcing boundary
- no OCR or network dependency inside R11 validation
- no weakening of builder or aggregator strictness

## 12. Runtime Artifact Boundary

This closeout does not add or preserve runtime artifacts in Git.

The following remain local runtime artifacts only and must not be committed:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- analysis JSON files
- validation reports
- scorecards
- other local outputs generated during manual inspection and validation

This document records the second non-bank validation outcome and fix boundary only. It does not promote runtime artifacts into source control.
