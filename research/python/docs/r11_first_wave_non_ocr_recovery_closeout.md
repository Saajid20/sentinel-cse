# R11.14D First-Wave Non-OCR Recovery Closeout

## 1. Closeout Decision

R11.14D closes the first-wave non-OCR parser/layout recovery work.

After R11.14, the first-wave non-OCR hard cases are no longer parser-crash or zero-metric blockers:

- `WATA.N0000` is a clean recovered metric case
- `LDEV.N0000` is a clean recovered metric case
- `RENU.N0000` is a partial manual-review recovery case
- `WIND.N0000` is a partial manual-review recovery case

The remaining first-wave deferred cases are OCR-needed filings:

- `GLAS.N0000`
- `LALU.N0000`

This closeout does not claim OCR support and does not introduce a generic table reconstruction engine. It records the deterministic parser/layout recovery boundary reached by R11.14.

## 2. First-Wave Status Before R11.14

Before R11.14, the first-wave deferred set included parser, layout, and OCR gaps:

- `WATA.N0000`: parser/layout hard case with malformed extracted financial value and later metric conflicts
- `RENU.N0000`: parser-error case with malformed extracted financial value `7)`
- `LDEV.N0000`: inspectable manual-review metric-gap case missing group profit growth
- `WIND.N0000`: inspectable zero-metric block-reconstruction case
- `GLAS.N0000`: OCR required because no usable pypdf text was extractable
- `LALU.N0000`: OCR required because no usable pypdf text was extractable

These cases were outside the initial clean statement-level benchmark path because they exposed failure modes that required deterministic hardening before broader validation.

## 3. First-Wave Status After R11.14

R11.14 recovered the non-OCR cases as follows:

- `WATA.N0000` moved to a clean metric case with no conflicts and no manual review
- `LDEV.N0000` moved to a clean metric case with no conflicts and no manual review
- `RENU.N0000` moved from parser error to partial metric recovery
- `WIND.N0000` moved from zero metrics to partial metric recovery

`RENU.N0000` and `WIND.N0000` still require manual review because `group_total_liabilities_growth` is missing and was intentionally not synthesized.

`GLAS.N0000` and `LALU.N0000` remain deferred because their failure mode is OCR/no-text, not deterministic pypdf parser/layout behavior.

## 4. Summary Table

| Ticker | Original Category | Final Category | Recovered Metrics | Manual Review Required | Remaining Gap |
| --- | --- | --- | --- | --- | --- |
| `WATA.N0000` | Parser/layout hard case | Clean recovered metric case | `group_profit_for_the_period_yoy_growth`, `group_total_assets_growth`, `group_total_equity_growth`, `group_total_liabilities_growth` | `false` | None |
| `LDEV.N0000` | Manual-review metric-gap case | Clean recovered metric case | `group_profit_for_the_period_yoy_growth`, `group_total_assets_growth`, `group_total_equity_growth`, `group_total_liabilities_growth` | `false` | None |
| `RENU.N0000` | Parser-error case | Partial manual-review recovery case | `group_profit_for_the_period_yoy_growth`, `group_total_assets_growth`, `group_total_equity_growth` | `true` | `group_total_liabilities_growth` missing |
| `WIND.N0000` | Zero-metric block-reconstruction case | Partial manual-review recovery case | `group_profit_for_the_period_yoy_growth`, `group_total_assets_growth`, `group_total_equity_growth` | `true` | `group_total_liabilities_growth` missing |
| `GLAS.N0000` | OCR required | Deferred OCR case | None | Not applicable | No extractable pypdf text |
| `LALU.N0000` | OCR required | Deferred OCR case | None | Not applicable | No extractable pypdf text |

## 5. Deterministic Recovery Types

R11.14 used several deterministic recovery types.

### Malformed Token Strictness

The pypdf financial token parser was tightened so malformed one-sided parenthesis tokens do not enter parsed financial values.

Examples rejected before value mapping:

- `(52,2620`
- `7)`

Balanced negatives such as `(52,262)` remain valid.

### Percent-Token Label Cleanup

Percent tokens are stripped during financial row label cleanup so metric labels do not inherit numeric tails.

Examples:

- `16%`
- `-65%`
- `24%`
- `(11%)`

Percent tokens are not emitted as parsed financial values in this path. They are used to keep canonical labels clean.

### Statement-Type Metric Filtering

Verified income and balance-sheet metrics are built only from appropriate primary statement types.

Income metrics require income-statement context. Balance-sheet metrics require balance-sheet context unless a narrow mixed-page recovery explicitly overrides the effective statement type.

This prevents equity statements, cash-flow pages, notes, unknown pages, and segmental analysis pages from producing false verified metrics.

### Quarter-Plus-Annual Layout Handling

WATA-style income rows with quarter and annual period blocks now use the annual group values for group annual metrics.

LDEV-style quarter/year variance rows are also recovered deterministically when the group income statement title and variance layout markers are present.

### Mixed-Page Balance-Section Handling

WATA page 5 contains a primary balance-sheet section on a page otherwise classified as income-statement context.

R11.14 detects the primary balance section using explicit group/company and date-header markers, then allows only primary balance-sheet rows such as total assets, total equity, and total liabilities to produce balance metrics.

### Side-by-Side Page Recovery

RENU page 1 contains multiple statements merged horizontally into single pypdf text lines.

R11.14 detects the merged-statement page using explicit statement markers and recovers only source-backed primary rows:

- `profit_for_the_period`
- `total_assets`
- `total_equity`

### Block Reconstruction Recovery

WIND pages 5 and 6 contain labels and values in separate pypdf text blocks.

R11.14 adds a narrow WIND-specific block recovery:

- page 5 consolidated income block recovers `profit_for_the_period`
- page 6 consolidated statement of financial position recovers `total_assets` and `total_equity`
- company statement pages are excluded
- `total_liabilities` is not synthesized

## 6. Why RENU and WIND Total Liabilities Were Not Synthesized

R11.14 intentionally did not synthesize missing total liabilities for `RENU.N0000` or `WIND.N0000`.

For RENU, the pypdf side-by-side extraction did not expose a clean explicit `Total Liabilities` row suitable for metric construction.

For WIND, explicit liability component rows are visible, including total non-current liabilities and total current liabilities, but there is no clean explicit primary `Total Liabilities` row.

Synthesizing total liabilities from components would introduce a policy and arithmetic derivation beyond the approved parser/layout recovery scope.

The R11.14 rule is:

- recover explicit source-backed primary rows
- do not infer missing expected metrics from component arithmetic unless a later milestone explicitly approves that behavior

This keeps partial recoveries deterministic, auditable, and appropriately marked for manual review.

## 7. Why GLAS and LALU Remain Deferred

`GLAS.N0000` and `LALU.N0000` remain deferred because their failure mode is OCR/no-text:

- no usable pypdf text is extractable
- deterministic text parser/layout hardening cannot recover absent text
- OCR support was not added in R11.14

These cases should be handled only after an OCR strategy is designed, approved, and validated separately.

## 8. Runtime Artifact Boundary

R11.14 recovery work used local runtime PDFs and local inspection outputs for verification.

The following remain runtime artifacts and must not be committed:

- PDFs under `.r10_runtime/`
- generated analysis JSON files
- validation reports
- manifests
- gold labels
- generated runtime outputs under `.r11_runtime/`

This closeout document is a checked-in documentation artifact. It does not include runtime JSON payloads, validation artifacts, or local PDF contents.

## 9. Relationship to Gold-Label Validation

R11.13 established the gold-label validation foundation and local runtime gold labels for the first clean benchmark cases:

- `DIMO.N0000`
- `AEL.N0000`
- `SAMP.N0000`
- `COMB.N0000`

R11.14 recovered additional hard non-OCR cases, but this closeout does not add or commit new gold labels.

The newly clean cases should be promoted into local runtime gold-label validation in a follow-up milestone after the parser/layout recovery branch is closed.

Recommended immediate additions are:

- `WATA.N0000`
- `LDEV.N0000`

`RENU.N0000` and `WIND.N0000` should remain manual-review partial-recovery cases unless a later milestone approves liability synthesis or discovers clean explicit total-liabilities source rows.

## 10. Recommended Next Phase

Recommended next phase:

- R11.14E: create local runtime gold labels for newly clean `WATA.N0000` and `LDEV.N0000`
- later: use `RENU.N0000` and `WIND.N0000` as manual-review partial-recovery cases
- later: design an OCR strategy for `GLAS.N0000` and `LALU.N0000`
- later: design generic table/block reconstruction only if repeated future cases justify it

R11.14 should be treated as a deterministic first-wave non-OCR parser/layout recovery milestone, not as OCR support, LLM-based data repair, or a generic table-reconstruction framework.
