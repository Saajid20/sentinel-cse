# R11.14C LDEV Recovery Closeout

## 1. Closeout Decision

R11.14C is complete for `LDEV.N0000` as a deterministic metric-gap recovery milestone.

`LDEV.N0000` moved from an inspectable manual-review case to a clean deterministic metric case:

- inspection completes
- `total_verified_metric_count: 4`
- `aggregated_metric_count: 4`
- `has_conflicts: false`
- `scorecard.manual_review_required: false`
- `missing_expected_metrics: []`

This closeout covers LDEV recovery only. It does not resolve the broader `WIND.N0000` layout gap or OCR-needed cases.

## 2. Original LDEV Gap

Before R11.14C2, `LDEV.N0000` inspected successfully but still required manual review.

It already produced the primary balance-sheet metrics:

- `group_total_assets_growth`
- `group_total_equity_growth`
- `group_total_liabilities_growth`

The missing expected metric was:

- `group_profit_for_the_period_yoy_growth`

Because the profit metric was absent, the deterministic scorecard remained incomplete and `manual_review_required` stayed true.

## 3. Root Cause

LDEV page 2 contains the group income statement row:

- `Profit/(Loss) for the Period (31,447) (168,393) + (81) 240,389 730,682 - 67`

The income statement layout is:

- `Quarter | Quarter | Year | Year`
- variance columns between the period blocks

The ordinary parser and normalization path extracted values from the row, but did not recover a clean annual group profit metric. The `+` and `-` variance-sign tokens polluted the row interpretation, and the annual values were not selected for group metric construction.

The issue was not caused by:

- OCR or missing extractable text
- R10 ingestion
- statement location
- metric aggregation
- scorecard logic

It was a deterministic parser/layout gap in the R11 pypdf inspection metric construction path.

## 4. Recovery Approach

R11.14C2 added a focused inspection-layer recovery for LDEV-style group income rows.

The recovery is deliberately narrow. It requires:

- `STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME-GROUP`
- `Quarter Quarter Year Year`
- `Variance`
- an explicit `Profit/(Loss) for the Period` row

The recovery rejects company income pages, including pages titled:

- `STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME-COMPANY`

For the LDEV group row, the recovery uses annual values rather than quarter values:

- `group_current: 240,389`
- `group_previous: 730,682`

It also preserves the reported annual variance when safely extractable:

- `reported: -67.0`

The recovered row is appended as a deterministic mapped item before metric construction, with an effective `INCOME_STATEMENT` statement type and source trace back to the original pypdf line.

## 5. Final LDEV Result

Final LDEV inspection result after R11.14C2:

- inspection completes
- `total_verified_metric_count: 4`
- `aggregated_metric_count: 4`
- `has_conflicts: false`
- `scorecard.manual_review_required: false`
- `missing_expected_metrics: []`

Recovered metric:

| Metric | Current | Previous | Calculated | Reported |
| --- | ---: | ---: | ---: | ---: |
| `group_profit_for_the_period_yoy_growth` | `240,389` | `730,682` | `-67.1` | `-67.0` |

The existing balance-sheet metrics remained present:

- `group_total_assets_growth`
- `group_total_equity_growth`
- `group_total_liabilities_growth`

No conflicts were introduced.

## 6. What Was Intentionally Not Changed

The following areas were intentionally left unchanged:

- R10 ingestion, lookup, and fetch logic
- OCR logic and OCR provider integration
- DeepSeek or other LLM provider logic
- `value_mapper.py`
- `metric_builder.py`
- `metric_aggregator.py`
- `scorecard_builder.py`
- ATrad, pipeline, strategy, broker, session, execution, order, and live-engine code

The fix was kept in the deterministic R11 pypdf inspection-layer recovery path.

## 7. Runtime Artifact Boundary

The LDEV recovery was validated with a local runtime PDF and local inspection output.

The following remain runtime artifacts and must not be committed:

- PDFs under `.r10_runtime/`
- analysis JSON files
- validation reports
- manifests
- gold labels
- generated runtime outputs under `.r11_runtime/`

This closeout document is a checked-in documentation artifact. It does not include runtime JSON payloads or local PDF contents.

## 8. Deterministic Parser/Layout Recovery, Not OCR or LLM

R11.14C did not use OCR and did not use an LLM to infer LDEV values.

The recovery is deterministic:

- page eligibility uses explicit group income statement markers
- layout eligibility uses fixed quarter/year variance markers
- row recovery uses a fixed explicit profit/loss pattern
- annual value selection is fixed and auditable
- reported variance handling is deterministic
- metric calculation, aggregation, and scorecard output remain deterministic

No DeepSeek call, network call, OCR API call, or LLM-based data repair was part of this recovery.

## 9. Recommended Next Step

Move to `WIND.N0000` diagnosis separately.

`WIND.N0000` is a broader label/value block-reconstruction problem. Its primary pages contain labels and values split across separate pypdf text blocks, so it should not be handled as a small LDEV-style row recovery. WIND needs its own focused diagnosis and approved implementation plan.
