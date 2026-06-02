# R11 Non-Bank Validation Baseline

## 1. Closeout Decision

R11.9A is complete as a documentation-only closeout for the first non-bank validation baseline.

This is a successful non-bank baseline, not a clean full validation closeout. The deterministic R11 path generalized to a non-bank CSE financial report, but the resulting scorecard still required manual review because of an aggregated metric conflict.

## 2. Scope

This closeout covers one non-bank baseline case only:

- company: `Access Engineering PLC`
- ticker: `AEL.N0000`
- report: Interim Financial Statements for the period ended / twelve months ended `31 March 2026`
- R11 focus range: pages `2-6`

The purpose of R11.9A was to verify that the existing deterministic validation path could classify and validate a first non-bank financial report without widening the system boundary.

## 3. R10 Sourcing Path

R10 remained the source boundary for this baseline.

The source path was:

1. R10 financial reports discovery identified the report source.
2. The PDF was then obtained through the explicit CSE PDF URL fetch path.
3. R11 consumed the resulting local R10-sourced PDF.

R11 did not perform source discovery or source downloading for this validation.

## 4. AEL Validation Result

Case:

- `AEL.N0000`
- `Access Engineering PLC`

Statement classifications:

- page `2`: `INCOME_STATEMENT` `HIGH`
- page `3`: `INCOME_STATEMENT` `HIGH`
- page `4`: `BALANCE_SHEET` `HIGH`
- page `5`: `EQUITY_STATEMENT` `HIGH`
- page `6`: `CASH_FLOW` `HIGH`

Validation outcome:

- verified metric count: `6`
- analysis JSON validation result: `PASS`
- scorecard: produced
- manual review required: `True`

## 5. What Passed

The following checks passed for the AEL baseline:

- page `2` `INCOME_STATEMENT` passed
- page `3` `INCOME_STATEMENT` passed
- page `4` `BALANCE_SHEET` passed
- page `5` `EQUITY_STATEMENT` passed
- page `6` `CASH_FLOW` passed
- scorecard present passed

What this proves:

- statement classification generalized well from the earlier bank cases into a first non-bank case
- the deterministic R11 path can consume a local R10-sourced non-bank PDF and produce a valid analysis JSON plus scorecard
- the focused page range `2-6` was sufficient to cover the core statements for this report

## 6. What Did Not Fully Pass / Manual-Review Boundary

This was not a clean fully automatic validation because the produced scorecard required manual review.

Manual review reason:

- aggregated metric conflicts detected: `group_profit_for_the_period_yoy_growth`

Interpretation:

- the baseline succeeded at the statement-classification and per-statement validation level
- the remaining issue is in metric aggregation behavior, not in basic report acquisition or statement identification
- repeated or non-bank-specific profit rows are the current likely source of the conflict

## 7. Known Limitations

Current limitations exposed by this baseline:

- only one non-bank case has been validated so far
- the closeout does not establish clean non-bank metric aggregation across repeated profit-row patterns
- the manual-review result means this milestone does not yet prove full non-bank scorecard reliability
- this result should not be generalized to all non-bank CSE layouts or all interim-report structures

## 8. Recommended Next Phase

Recommended next phase:

- `R11.9B` metric conflict investigation / non-bank metric handling

Priority focus:

- inspect why `group_profit_for_the_period_yoy_growth` produced an aggregated conflict
- determine whether repeated profit rows, alternative non-bank labeling, or aggregation precedence rules need adjustment
- keep the deterministic boundary intact while improving non-bank metric handling

## 9. Runtime Artifact Boundary

This closeout does not add or preserve runtime artifacts in Git.

The following remain local runtime artifacts only and must not be committed:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- analysis JSON files
- validation reports
- scorecards
- other local runtime outputs generated during manual validation

This document records the baseline result and boundary only. It does not promote runtime artifacts into source control.
