# R11.14C WIND Partial Recovery Closeout

## 1. Closeout Decision

R11.14C is complete for `WIND.N0000` as a deterministic partial metric-gap recovery milestone.

`WIND.N0000` moved from a zero-metric block-reconstruction case to an inspectable partial scorecard case:

- inspection completes
- `total_verified_metric_count: 3`
- `aggregated_metric_count: 3`
- `has_conflicts: false`
- `scorecard.manual_review_required: true`

The remaining manual-review state is expected because `group_total_liabilities_growth` is still missing.

## 2. Original WIND Gap

Before R11.14C4, `WIND.N0000` inspected successfully but produced no verified metrics:

- `total_verified_metric_count: 0`
- `aggregated_metric_count: 0`
- `has_conflicts: false`
- `scorecard.manual_review_required: true`

The missing expected metrics were:

- `group_profit_for_the_period_yoy_growth`
- `group_total_assets_growth`
- `group_total_liabilities_growth`
- `group_total_equity_growth`

WIND was the remaining first-wave non-OCR metric-gap case after WATA, RENU, and LDEV recovery work.

## 3. Root Cause

WIND is a pypdf block reconstruction gap.

The primary statements have extractable text, but pypdf separates labels and values into different text blocks rather than keeping label and values on the same line.

This affected:

- page 5: primary consolidated income statement
- page 6: primary consolidated statement of financial position

The issue was not caused by:

- OCR or missing extractable text
- R10 ingestion
- primary statement location
- strict financial value parsing
- metric aggregation
- scorecard logic

The ordinary row parser expects label and values to appear together on a single extracted line. WIND's primary pages violate that assumption.

## 4. R11.14C4 Recovery Approach

R11.14C4 added a narrow WIND-specific inspection-layer block recovery.

It does not introduce a generic table reconstruction engine.

### Consolidated Income Block

The recovery detects WIND consolidated income blocks using explicit markers:

- `CONSOLIDATED INCOME STATEMENT`
- `Profit after Taxation`
- `Three Months Ended 31st March Twelve Months Ended 31st March`
- `Change % Change %`

It also excludes company income pages:

- `COMPANY INCOME STATEMENT`

When the marker-gated layout is present, the recovery maps:

- `Profit after Taxation` to `profit_for_the_period`

It uses the annual current and previous values:

- `current: 2,099,532,182`
- `previous: 2,249,689,817`

### Consolidated Statement of Financial Position Block

The recovery detects WIND consolidated balance-sheet blocks using:

- `CONSOLIDATED STATEMENT OF FINANCIAL POSITION`
- `Total Assets`
- `Total Equity`
- `As at 31.03.2026`
- `As at 31.03.2025`

It excludes company statement pages:

- `COMPANY STATEMENT OF FINANCIAL POSITION`

Only explicit source-backed rows are recovered:

- `total_assets`
- `total_equity`

Each recovered item carries a source trace back to the source label line and selected current/previous value lines.

## 5. Final WIND Result

Final WIND inspection result after R11.14C4:

- inspection completes
- `total_verified_metric_count: 3`
- `aggregated_metric_count: 3`
- `has_conflicts: false`
- `scorecard.manual_review_required: true`

Recovered metrics:

| Metric | Calculated |
| --- | ---: |
| `group_profit_for_the_period_yoy_growth` | `-6.67` |
| `group_total_assets_growth` | `11.84` |
| `group_total_equity_growth` | `9.59` |

Remaining missing expected metric:

- `group_total_liabilities_growth`

No conflicts were introduced.

## 6. Why Total Liabilities Was Not Synthesized

R11.14C4 intentionally did not synthesize total liabilities.

WIND page 6 contains explicit liability component rows, including:

- `Total Non-Current Liabilities`
- `Total Current Liabilities`

However, there is no clean explicit primary row for:

- `Total Liabilities`

Synthesizing total liabilities from component totals would introduce a policy and arithmetic derivation beyond this recovery's approved scope.

The R11.14C4 rule is:

- recover explicit source-backed primary rows only
- do not infer missing expected metrics from component arithmetic unless a later milestone explicitly approves that behavior

This keeps WIND recovery partial, deterministic, and auditable.

## 7. What Was Intentionally Not Changed

The following areas were intentionally left unchanged:

- R10 ingestion, lookup, and fetch logic
- OCR logic and OCR provider integration
- DeepSeek or other LLM provider logic
- `pypdf_row_parser.py`
- `line_item_mapper.py`
- `value_mapper.py`
- `metric_builder.py`
- `metric_aggregator.py`
- `scorecard_builder.py`
- ATrad, pipeline, strategy, broker, session, execution, order, and live-engine code

The fix was kept in the deterministic R11 pypdf inspection-layer recovery path.

## 8. Runtime Artifact Boundary

The WIND recovery was validated with a local runtime PDF and local inspection output.

The following remain runtime artifacts and must not be committed:

- PDFs under `.r10_runtime/`
- analysis JSON files
- validation reports
- manifests
- gold labels
- generated runtime outputs under `.r11_runtime/`

This closeout document is a checked-in documentation artifact. It does not include runtime JSON payloads or local PDF contents.

## 9. Deterministic Parser/Layout Recovery, Not OCR or LLM

R11.14C did not use OCR and did not use an LLM to infer WIND values.

The recovery is deterministic:

- page eligibility uses explicit consolidated statement markers
- company pages are explicitly excluded
- block recovery uses fixed label/value alignment rules
- only approved source-backed metrics are recovered
- total liabilities is not synthesized
- metric calculation, aggregation, and scorecard output remain deterministic

No DeepSeek call, network call, OCR API call, or LLM-based data repair was part of this recovery.

## 10. Recommended Next Phase

Recommended next phase:

- close and merge the `r11/ldev-wind-metric-gap-triage` branch after documentation
- defer generic table/block reconstruction to a later phase
- keep OCR-needed cases `GLAS.N0000` and `LALU.N0000` deferred until an OCR path is planned and approved

WIND is now partially recovered and no longer a zero-metric case. Its remaining total-liabilities gap should be handled only if a later milestone explicitly approves liability synthesis or finds a clean explicit total-liabilities source row.
