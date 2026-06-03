# R11.14B RENU Partial Recovery Closeout

## 1. Closeout Decision

R11.14B is complete for `RENU.N0000` as a deterministic partial recovery milestone.

`RENU.N0000` moved from a first-wave parser-error deferred case to an inspectable partial scorecard case:

- inspection completes without parser crash
- `total_verified_metric_count: 3`
- `aggregated_metric_count: 3`
- `has_conflicts: false`
- `scorecard.manual_review_required: true`

The remaining manual-review state is expected because `group_total_liabilities_growth` is still missing.

## 2. Original RENU Failure

`RENU.N0000` was originally deferred because pypdf extraction produced a malformed financial token:

- `invalid financial value: "7)"`

That token appeared in a notes/public-shareholding area, not in a primary financial metric row. Before R11.14A parser hardening, it could abort deterministic inspection before RENU reached metric triage.

## 3. WATA Fixes That Already Helped RENU

Several R11.14A fixes from the WATA recovery improved RENU before any RENU-specific patch:

- malformed token strictness stopped one-sided parenthesis tokens such as `7)` from entering parsed financial values
- statement-type metric filtering prevented equity and notes pages from becoming false verified metric sources
- percent-token cleanup made label cleanup safer, although RENU's main remaining issue was not percent suffixes

After those fixes, RENU no longer crashed. It became inspectable but metric-poor.

## 4. RENU Side-by-Side Page Extraction Issue

RENU page 1 contains multiple statements merged horizontally into single pypdf text lines:

- statement of financial position on the left
- profit/loss and comprehensive income in the middle
- cash-flow statement on the right

This caused ordinary row parsing and canonicalization to see polluted labels and mixed value sequences. Examples included:

- `TOTAL ASSETS 12,629,424 10,790,151 ... Marketing expenses ...`
- `Retained earnings ... Profit for the period 407,066 ... 1,357,854 689,830 97 ...`
- `Total Equity 12,485,306 10,655,410 Other Comprehansive Income`

Forcing page 1 to `INCOME_STATEMENT` or `BALANCE_SHEET` was not enough. The failure was a side-by-side row recovery/layout issue, not just page-level statement classification.

## 5. R11.14B2 Recovery Approach

R11.14B2 added deterministic RENU-style side-by-side page recovery in the inspection-layer metric construction path.

The recovery detects a combined RENU-style page using explicit merged-statement markers:

- `statement of profit or loss`
- `statement of cash flows`
- `statement of financial position`
- `cash flow from operating activities`
- `total assets`

When those markers are present, R11 recovers only explicit primary embedded rows before metric construction:

- `profit_for_the_period` as `INCOME_STATEMENT`
- `total_assets` as `BALANCE_SHEET`
- `total_equity` as `BALANCE_SHEET`

The recovered rows are appended as deterministic mapped items with source traces back to the original pypdf line.

The recovery does not loosen generic value parsing, statement filtering, metric building, aggregation, or scorecard logic.

## 6. Final RENU Result

Final RENU inspection result after R11.14B2:

- inspection completes without parser crash
- `total_verified_metric_count: 3`
- `aggregated_metric_count: 3`
- `has_conflicts: false`
- `scorecard.manual_review_required: true`

Recovered metrics:

| Metric | Current | Previous | Calculated | Reported |
| --- | ---: | ---: | ---: | ---: |
| `group_total_assets_growth` | `12,629,424` | `10,790,151` | `17.05` |  |
| `group_profit_for_the_period_yoy_growth` | `1,357,854` | `689,830` | `96.84` | `97.0` |
| `group_total_equity_growth` | `12,485,306` | `10,655,410` | `17.17` |  |

The profit metric's reported value differs from the deterministic calculation by `-0.16` percentage points because the report rounds to `97.0`.

## 7. What Remains Missing

The remaining missing expected metric is:

- `group_total_liabilities_growth`

RENU remains a manual-review case because the deterministic pypdf text did not expose a clean explicit `Total Liabilities` row suitable for metric construction.

## 8. Why Total Liabilities Was Not Synthesized

R11.14B2 intentionally did not synthesize total liabilities from other rows.

The source text includes current and non-current liability-related rows, but the pypdf extraction is side-by-side and noisy. Constructing total liabilities from components would introduce a policy decision and arithmetic derivation that is outside this recovery's scope.

The safer R11.14B rule is:

- recover explicit primary rows only
- do not infer or synthesize missing expected metrics unless a later milestone explicitly approves that behavior

This keeps RENU partial recovery deterministic and auditable.

## 9. Runtime Artifact Boundary

The RENU recovery was validated with a local runtime PDF and local inspection output.

The following remain runtime artifacts and must not be committed:

- PDFs under `.r10_runtime/`
- analysis JSON files
- validation reports
- manifests
- gold labels
- generated runtime outputs under `.r11_runtime/`

This closeout document is a checked-in documentation artifact. It does not include runtime JSON payloads or local PDF contents.

## 10. Deterministic Parser/Layout Recovery, Not OCR or LLM

R11.14B did not use OCR and did not use an LLM to infer values.

The recovery is deterministic:

- page detection uses explicit text markers
- row recovery uses fixed regex patterns
- values are parsed with the existing strict financial value parser
- recovered rows carry effective statement types for existing A2 metric filtering
- metric calculation and aggregation remain deterministic

No DeepSeek call, network call, OCR API call, or LLM-based data repair was part of this recovery.

## 11. Recommended Next Phase

Recommended next phase:

- merge the current `r11/parser-error-triage` branch after closeout
- later handle `LDEV.N0000` and `WIND.N0000` as metric-gap/manual-review cases
- defer OCR-needed cases `GLAS.N0000` and `LALU.N0000` until an OCR path is planned and approved

RENU is now partially recovered and no longer blocks on parser error. Its remaining total-liabilities gap should be handled only if a later milestone explicitly approves row synthesis or a safer source-row recovery.
