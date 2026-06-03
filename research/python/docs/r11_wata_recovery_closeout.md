# R11.14A WATA Recovery Closeout

## 1. Closeout Decision

R11.14A is complete for `WATA.N0000` as a deterministic parser and layout recovery milestone.

`WATA.N0000` moved from a first-wave deferred parser/layout hard case to a clean deterministic inspection result:

- inspection completes without parser crash
- `total_verified_metric_count: 4`
- `aggregated_metric_count: 4`
- `has_conflicts: false`
- `scorecard.manual_review_required: false`

This closeout covers WATA recovery only. It does not declare that all first-wave deferred cases are resolved.

## 2. Original WATA Failure

`WATA.N0000` was originally deferred because pypdf extraction produced a malformed financial token:

- `invalid financial value: "(52,2620"`

After the parser stopped aborting, WATA exposed additional deterministic layout issues:

- false profit-growth conflicts from equity, segmental, and company income rows
- polluted income labels caused by percent tokens
- quarter-vs-annual income layout confusion
- missing balance-sheet metrics from a mixed page whose page-level classification was `INCOME_STATEMENT`

## 3. Step-by-Step Fixes

### R11.14A1 - Malformed Token Strictness

The pypdf row parser was tightened so one-sided parenthesis tokens no longer enter parsed financial values.

Rejected malformed examples:

- `(52,2620`
- `7)`

Valid examples remain supported:

- `(52,262)`
- `1,268`
- `52,262`
- `0.65`
- missing-value dashes where already supported

`value_mapper.py` stayed strict. The fix prevents malformed tokens from reaching it as financial values.

### R11.14A2 - Statement-Type Metric Filtering

Metric construction was filtered by primary statement type.

Income-statement metrics now require `INCOME_STATEMENT` pages. Balance-sheet metrics require `BALANCE_SHEET` pages unless explicitly recovered by mixed-page handling.

This prevents equity statements, cash-flow pages, notes, unknown pages, and segmental analysis pages from producing false verified income or balance-sheet metrics.

### R11.14A4 - Percent-Token Label Cleanup

Percent tokens are now stripped during financial row label cleanup.

Examples:

- `16%`
- `-65%`
- `24%`
- `(11%)`

Percent tokens are not emitted as parsed financial values. They are used only to remove trailing numeric/percent tails from labels.

This allowed WATA rows such as:

- `Profit for the period 146,379 412,352 -65% 2,330,446 1,884,909 24%`

to normalize cleanly as:

- `profit_for_the_period`

### R11.14A6 - WATA-Style Quarter-Plus-Annual Income Layout

WATA income statement rows use period blocks:

- `Quarter ended 31 March`
- `12 months ended 31 March`

After percent cleanup, the parser emits four numeric values:

- `value_1`: quarter current
- `value_2`: quarter previous
- `value_3`: annual current
- `value_4`: annual previous

For consolidated/group income rows, R11.14A6 selects `value_3` and `value_4` for group annual metric construction.

Recovered WATA profit metric:

- metric: `group_profit_for_the_period_yoy_growth`
- current: `2,330,446`
- previous: `1,884,909`
- calculated YoY: `23.64`

Company income pages and mixed duplicate company income sections do not produce group profit metrics.

### R11.14A8 - Mixed-Page Balance-Section Recovery

WATA page 5 is a mixed page.

The true balance-sheet section is on page 5 lines 4-51:

- line 4: `Group Company`
- line 5: `31.03.2026 31.03.2025 31.03.2026 31.03.2025`
- lines 6-51: primary Statement of Financial Position rows

Later page 5 lines 60-87 contain duplicated company income-style rows and should not produce group income metrics.

R11.14A8 detects the mixed-page balance section using:

- `Group Company` header
- four-date balance-sheet header
- primary rows for `Total Assets`, `Total Equity`, and `Total Liabilities`

Only those primary balance-sheet rows are treated as `BALANCE_SHEET` for metric construction. Fair-value and note pages remain excluded.

## 4. Final WATA Validation Result

Final WATA inspection result:

- inspection completes without parser crash
- `total_verified_metric_count: 4`
- `aggregated_metric_count: 4`
- `has_conflicts: false`
- `scorecard.manual_review_required: false`

Recovered metrics:

| Metric | Current | Previous | Calculated |
| --- | ---: | ---: | ---: |
| `group_profit_for_the_period_yoy_growth` | `2,330,446` | `1,884,909` | `23.64` |
| `group_total_assets_growth` | `8,600,043` | `8,713,149` | `-1.3` |
| `group_total_equity_growth` | `3,010,438` | `3,747,239` | `-19.66` |
| `group_total_liabilities_growth` | `5,589,606` | `4,965,910` | `12.56` |

## 5. What Was Fixed

R11.14A fixed WATA by hardening deterministic parser and layout handling:

- malformed pypdf financial tokens are rejected before value mapping
- non-primary statement pages no longer produce false verified growth metrics
- percent suffixes no longer pollute canonical line-item labels
- WATA-style quarter-plus-annual income rows use annual group values
- WATA mixed-page balance rows recover primary balance-sheet metrics
- fair-value and note pages remain excluded from primary balance-sheet metrics

## 6. What Was Intentionally Not Changed

The following areas were intentionally left unchanged:

- R10 ingestion, lookup, and fetch logic
- OCR logic and OCR provider integration
- DeepSeek or other LLM provider logic
- `value_mapper.py` strict financial value parsing
- `metric_builder.py`
- `metric_aggregator.py`
- `scorecard_builder.py`
- ATrad, pipeline, strategy, broker, session, execution, order, and live-engine code

The WATA recovery was kept in the deterministic R11 pypdf inspection/parser path.

## 7. Runtime Artifact Boundary

The WATA recovery uses local runtime PDFs and inspection output only for verification.

The following must remain uncommitted runtime artifacts:

- PDFs under `.r10_runtime/`
- analysis JSON files
- validation reports
- manifests
- gold labels
- generated runtime outputs under `.r11_runtime/`

This closeout document is a checked-in documentation artifact. It does not include runtime JSON payloads or local PDF contents.

## 8. Why This Does Not Yet Prove OCR Support

WATA recovery used extractable pypdf text. It does not exercise OCR.

Cases such as `GLAS.N0000` and `LALU.N0000`, which have no extractable pypdf text and require OCR, remain separate OCR-needed cases. WATA proves that deterministic parsing and layout handling can recover a hard text-extraction layout case, not that image-only or scan-only filings are supported.

## 9. Why This Is Not an LLM Fix

R11.14A did not use an LLM to infer WATA values.

The recovery is deterministic:

- token recognition is regex/parser based
- label cleanup is parser based
- statement filtering is explicit
- period-block handling is explicit
- mixed-page balance recovery is marker based
- metric calculation uses deterministic arithmetic
- aggregation and scorecard output remain deterministic

No DeepSeek call, network call, OCR API call, or LLM-based data repair was part of this recovery.

## 10. Recommended Next Step

Retest `RENU.N0000` with the WATA fixes before adding any RENU-specific patch.

RENU originally failed with a malformed financial value token:

- `invalid financial value: "7)"`

R11.14A1 should already prevent that parser abort. The next step should be a focused RENU rerun and diagnosis to determine whether remaining gaps are metric coverage, layout handling, statement classification, or a RENU-specific parser edge.
