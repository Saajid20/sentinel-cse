# R11.15B ACME Clean Recovery Closeout

## 1. Closeout Decision

R11.15B is complete for `ACME.N0000` as a deterministic label-derivation and column-block
recovery milestone, and as the first clean gold-label promotion out of the R11.15A
discovery pass.

`ACME.N0000` moved from a `MANUAL_REVIEW_CANDIDATE` with one missing core metric to a clean
deterministic inspection result:

- inspection completes without parser crash
- `total_verified_metric_count: 4`
- `aggregated_metric_count: 4`
- `has_conflicts: false`
- `scorecard.manual_review_required: false`
- `missing_expected_metrics: []`

This matters beyond ACME itself. Every gold label in the validation base before this one is
either a pre-existing clean case (`DIMO.N0000`, `AEL.N0000`, `SAMP.N0000`, `COMB.N0000`) or a
recovered/manual-review case (`WATA.N0000`, `LDEV.N0000`, `RENU.N0000`, `WIND.N0000`).
R11.15A classified all six of its eligible tickers as `MANUAL_REVIEW_CANDIDATE` or
`PARSE_GAP` and explicitly set `recommended_clean_promotion_count: 0`. ACME is the first
promotion of a discovery-pass candidate to `CLEAN_SCORECARD`.

This closeout covers ACME only. It does not reclassify `CITH.N0000`, `CITW.N0000`,
`HVA.N0000`, `REEF.N0000`, or `RWSL.N0000`.

## 2. Original ACME Gap

The ACME baseline produced three of four expected core metrics:

- `group_total_assets_growth`
- `group_total_equity_growth`
- `group_total_liabilities_growth`

`group_profit_for_the_period_yoy_growth` was absent, so
`missing_expected_metrics` carried it, `earnings_quality` stayed `UNKNOWN`, and
`scorecard.manual_review_required` was `true`.

The gap was not a locator gap. ACME page 2
(`CONSOLIDATED STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME`) already
classified as `INCOME_STATEMENT` with `HIGH` confidence, and the profit row was present in
extracted text.

## 3. Root Cause

pypdf emits ACME's parenthesised percent cells with an internal space. The published cell
`(63%)` arrives as `( 63%)`.

The source row on page 2 extracts as:

```
Profit / (Loss) for the Period (313,538)       (192,078)       ( 63%)          (462,860)       (405,923)       ( 14%)
```

`strip_numeric_tokens_from_label` splits on whitespace and walks the token list
right-to-left, counting trailing value tokens until one fails to match
`_STRIPPABLE_VALUE_TOKEN_PATTERN`. The split percent cell tokenizes as two halves, `(` and
`14%)`, and neither half is a valid token: `14%)` carries an unbalanced closing paren.

So the very first token examined fails. `trailing_value_count` stays `0`, the strip is a
no-op, and the **entire line** — label plus all six numeric cells — becomes the label. That
label falls through to the `snake_case_name` fallback, producing a canonical name absent
from `VERIFIED_GROWTH_METRIC_MAP`, and `build_growth_metric_for_item` returns `None`
silently at `metric_builder.py:110`.

Two things are worth stating plainly, because both were plausible first guesses and both
are wrong:

- **The alias was never the problem.** `Profit / (Loss) for the Period` maps correctly. The
  label never got the chance to be canonicalized, because the numeric tail was still
  attached to it.
- **The failure is silent by design.** `metric_builder` returning `None` for an unrecognised
  canonical name is correct behaviour, not a defect. It is exactly what keeps unrecognised
  rows from becoming metrics. The cost is that a tokenization bug upstream surfaces only as
  a missing metric far downstream, with no warning attached.

## 4. Why ACME Is a Genuinely New Layout

Before writing anything ACME-specific, all four existing layout detectors were probed
directly against ACME pages 2 and 3. All four return `False` on both pages:

| Detector | ACME page 2 | ACME page 3 |
| --- | --- | --- |
| `_table_has_ldev_quarter_year_variance_group_income_layout` | `False` | `False` |
| `_table_has_renu_side_by_side_combined_statement` | `False` | `False` |
| `_table_has_wind_consolidated_income_block` | `False` | `False` |
| `_table_has_wind_consolidated_balance_block` | `False` | `False` |

ACME differs from each existing recovery on a specific axis:

- **unlike WIND** — ACME's statement rows are single-line. WIND's recovery handles rows whose
  label and values are split across extracted lines.
- **unlike RENU** — ACME's group and company income statements are on separate pages (2 and
  3). RENU's recovery handles a side-by-side combined statement on one page.
- **unlike LDEV** — ACME has no variance columns. LDEV's recovery handles a
  quarter/year/variance column arrangement.
- **unlike WATA** — ACME's period pair is `For the three months ended` / `For the year ended`.
  WATA's header reads `Quarter ended` / `12 months ended`.

What ACME **shares** with WATA is the thing that actually governs value selection: four-value
rows in quarter-then-annual column order, group scope, no percent column consumed as a
value. That is why no ACME-specific recovery was written. WATA's existing
quarter-plus-annual remap already selects `value_3`/`value_4` for group annual metrics and
is correct for ACME unchanged. Only the phrasing that opens the gate needed extending.

This is the intended order of preference from the extraction philosophy: reuse the existing
layout-specific recovery, widen only the explicit marker list, do not add a parallel
detector for a layout that is not actually new.

## 5. The Three Patches

Commit `a09db00` carries three patches. They are not independent.

### (a) Label-derivation-only percent-cell collapse

`pypdf_row_parser.py` gained `_collapse_split_percent_cells`, which rejoins the
pypdf-inserted space in a parenthesised percent cell — `( 63%)` becomes `(63%)` — and is
applied **only** on the path into `strip_numeric_tokens_from_label`.

Deliberate boundaries:

- `_VALUE_TOKEN_PATTERN` is unchanged. Percent cells remain non-values and never become
  financial data.
- `raw_text` is untouched, so source-trace fidelity is preserved. The trace for the
  recovered metric still shows the original extracted line, spaces and all.
- The pattern requires a digit-and-percent-and-close-paren lookahead, so it collapses the
  split percent cell and nothing else.

### (b) Explicit quarter-block marker tuple

`_table_has_quarter_plus_annual_income_layout` hardcoded the literal `"quarter ended"`.
ACME's header reads `For the three months ended`. The literal was replaced with an explicit
`_QUARTER_PLUS_ANNUAL_QUARTER_MARKERS` tuple listing each accepted phrasing, mirroring the
existing `_QUARTER_PLUS_ANNUAL_HEADER_MARKERS` style.

This is an explicit marker addition, not regex widening. A new filing phrasing still
requires a deliberate, reviewable entry in the tuple.

### (c) Unresolved-annual-column-block guard

`_drop_unresolved_annual_column_block_income_candidates` drops income metric candidates from
a page that carries an annual period marker together with four-value income rows when the
quarter-plus-annual gate did **not** fire. It follows the existing R11.14A2 page-type
candidate-filtering pattern.

The reasoning: such a page has two period blocks, but if the gate did not fire, this filing
words its quarter block in a way the explicit markers do not cover, so which block occupies
`value_1`/`value_2` is unknown. `COMB_FOUR_COLUMN_DUAL_SCOPE_MAP` assigns
`value_1`/`value_2` to `group_current`/`group_previous` unconditionally, and patch (a) makes
these rows candidates for the first time. Without (c), those rows would be published as
annual group figures on the strength of an assumption nothing verified.

## 6. (a) and (b) Are Interdependent — Never Revert Them Separately

This is the single most important operational fact in this closeout.

Each patch was disabled in isolation, in memory, against the real ACME PDF. Results:

| Configuration | `group_profit_for_the_period_yoy_growth` | Aggregated | `manual_review_required` |
| --- | --- | ---: | --- |
| shipped `a09db00` — (a)+(b)+(c) | `-14.03` from `-462,860` / `-405,923` | 4 | `false` |
| (a) reverted | absent — row tail stranded in the label again | 3 | `true` |
| (b) reverted, (c) enabled | absent — guard (c) correctly drops the candidate | 3 | `true` |
| (c) disabled, (b) present | `-14.03` — gate fires, guard never applies | 4 | `false` |

Reverting (a) alone re-strands the row tail inside the label and the metric disappears.
Reverting (b) alone leaves the quarter-plus-annual gate closed, so guard (c) drops the
candidate and the metric disappears. **Either way the metric vanishes.** They must be
reverted together or not at all.

Note the fourth row: with (b) in place the gate fires, so guard (c) is never reached on
ACME. Guard (c) is not what makes ACME work. It is what makes ACME's *failure mode* safe,
which is a different and more important property.

## 7. Guard (c)'s Empirical Validation

The counterfactual that matters is (b) reverted **and** (c) disabled — the shape the code
would have had if patch (a) had shipped alone, without the marker addition and without the
guard. Measured on the real ACME PDF:

```
group_profit_for_the_period_yoy_growth = -63.23
  inputs: current -313,538   previous -192,078
```

That is the **quarter** movement, published as annual group YoY growth, against a true
annual value of `-14.03` from `-462,860` / `-405,923`. The number is not a rounding
difference or a sign flip. It is a different financial fact, and it would have looked
entirely legitimate: correct metric name, correct entity scope, correct row label, a source
trace pointing at a real line on a real page of a real filing.

One correction to how this has been summarised previously. On ACME *specifically*, the
unguarded run does not go unnoticed: page 3, the company income page, produces a second
occurrence, the aggregator reports `conflict: true` with reason
`calculated change percentages differ beyond tolerance`, and the scorecard falls to
`manual_review_required: true`. So ACME itself would have been caught.

But it would have been caught **incidentally**, for a reason unrelated to the defect —
because this particular issuer publishes a separate company income page, and because with
(b) reverted page 3 never reaches the group-title check that normally excludes it. A filing
that publishes only a consolidated income statement produces exactly one occurrence, raises
no conflict, and reports `-63.23` as a clean verified metric with
`manual_review_required: false`. Nothing anywhere in the pipeline would flag it.

That is the concrete evidence for the principle. A missing metric costs one manual review.
A wrong metric that presents as clean costs the credibility of every metric beside it.
Missing is acceptable; wrong is not.

For the record, on ACME the two candidate paths differ by more than the guard:
`_table_has_company_income_statement_markers` returns `False` on page 3 — the `- COMPANY`
title suffix is not among its markers. In shipped code page 3 is excluded by
`_table_has_group_income_statement_title_markers` returning `False` inside the
quarter-plus-annual branch, which is itself reachable only because of patch (b). Company
discrimination on ACME therefore depends on (b) as well.

## 8. Blast Radius

Re-measured for this closeout, independently of the recovery commit, by running every local
real PDF twice in the same process — once with (a), (b) and (c) neutralised in memory to
emulate pre-`a09db00` behaviour, once as shipped — and diffing aggregated metric values,
conflict flags, occurrence counts and the full scorecard.

**ACME is the only change.** Result across all 15 local PDFs:

| Ticker | Result |
| --- | --- |
| `ACME.N0000` | changed — see below |
| `AEL.N0000`, `CITH.N0000`, `CITW.N0000`, `DIMO.N0000`, `HVA.N0000`, `LDEV.N0000`, `REEF.N0000`, `RENU.N0000`, `RWSL.N0000`, `SAMP.N0000`, `WATA.N0000`, `WIND.N0000` | identical |
| `GLAS.N0000`, `LALU.N0000` | identical — both still raise `R11ExtractionError` (`No extractable baseline table/text pages found`), OCR-required, unchanged |

ACME before and after:

| | before | after |
| --- | --- | --- |
| `group_profit_for_the_period_yoy_growth` | absent | `-14.03` |
| aggregated metric count | 3 | 4 |
| `earnings_quality` | `UNKNOWN` | `DETERIORATING` |
| `missing_expected_metrics` | `["group_profit_for_the_period_yoy_growth"]` | `[]` |
| `manual_review_required` | `true` | `false` |

`WIND.N0000` deserves an explicit note. Its header carries `Three Months Ended` /
`Twelve Months Ended`, which now matches both the new quarter marker tuple and the existing
annual marker tuple. WIND does not regress: its aggregated metrics, conflict flags and
scorecard are identical before and after. WIND reaches metric construction through its own
`_table_has_wind_consolidated_income_block` recovery, whose items are appended by
`_append_wind_block_recovered_items` before `_prepare_mapped_items_for_metric_build` — and
therefore before the quarter-plus-annual path and guard (c) — ever run.

## 9. Final ACME Result and Gold Label

Recovered metrics:

| Metric | Current | Previous | Calculated |
| --- | ---: | ---: | ---: |
| `group_profit_for_the_period_yoy_growth` | `-462,860` | `-405,923` | `-14.03` |
| `group_total_assets_growth` | `1,946,562` | `1,863,027` | `4.48` |
| `group_total_equity_growth` | `508,245` | `-518,474` | `198.03` |
| `group_total_liabilities_growth` | `1,438,317` | `2,381,501` | `-39.6` |

All four have `occurrence_count: 1` and `conflict: false`.

Scorecard: `earnings_quality: DETERIORATING`, `revenue_trend: UNKNOWN`,
`margin_trend: UNKNOWN`, `balance_sheet_risk: LOW`, `cash_flow_quality: UNKNOWN`,
`capital_strength: HIGH`, `manual_review_required: false`.

A local runtime gold label was created following the clean-case pattern
(`dimo`/`ael`/`samp`/`comb`), not the manual-review pattern (`renu`/`wind`):

- `benchmark_level: CLEAN_SCORECARD`
- `manual_review_expected: false`
- expected statement pages 2 and 3 (`INCOME_STATEMENT`), 4 (`BALANCE_SHEET`),
  5 (`CASH_FLOW`), 6 (`EQUITY_STATEMENT`)
- all four metrics with current, previous and calculated values, `tolerance: 0.01`,
  `conflict_expected: false`
- full expected scorecard including `manual_review_required: false`

Validation result: **`PASS`, 16 passed, 0 failed, 0 manual-review checks.**

The gold label encodes what should be true, and was written from the source rows before it
was run against the analysis output. It was not adjusted to match what the analysis
produced.

## 10. Known Limitation — No Percent Cross-Check

The four-value quarter-plus-annual dual-scope map has no percent slot. Consequently, for
every ACME metric:

- `reported_change_percent` is `None`
- `matches_reported` is `None`
- the metric note reads `No reported change percentage was available for verification.`

This is the same limitation already recorded for WATA.

What makes ACME notable is that the cross-check genuinely exists in the source. The PDF
prints the annual movement as `( 14%)` on the same row, which independently corroborates
the calculated `-14.03`. That published figure is read during percent-stripping and then
discarded, because percent cells are deliberately not financial values.

Capturing it would need a new six-column quarter/annual map. `value_mapper.py:79` already
has a `group_reported_change_percent` slot, but the map it belongs to
(`COMB_SIX_COLUMN_MAP`) is dual-scope group/bank, not quarter/annual, so it cannot be reused
as-is.

**Flagged as future work. Not implemented here.** Adding a six-column map is a value-mapping
change with its own blast radius across every four-value filing, and it does not belong in a
validation-and-documentation task.

## 11. Correction to the Record — 15 Local PDFs, Not 16

Earlier reports stated 16 local real PDFs. The correct count is **15**.

`research/python/.r10_runtime/cse_report_pdfs/` holds 15 files. The `COMB.N0000` files that
inflated earlier counts are pytest temp fixtures under `.pytest_tmp*`, not real local source
PDFs. The R11.15A discovery report already records `available_local_pdf_count: 15`.

All blast-radius statements in this closeout are measured across those 15 files.

## 12. What Was Intentionally Not Changed

R11.15B is validation and documentation. No extraction, mapping, or analysis code was
modified in this task.

Unchanged across the recovery commit and this closeout:

- `metric_builder.py`
- `metric_aggregator.py`
- `scorecard_builder.py`
- `value_mapper.py` strict financial value parsing
- `line_item_mapper.py`
- statement locator markers and page classification
- R10 ingestion, lookup, and fetch logic
- OCR logic and OCR provider integration
- DeepSeek or other LLM provider logic
- ATrad, pipeline, strategy, broker, session, execution, order, and live-engine code

No network call, OCR call, or LLM call was made. No financial value was synthesized: the
recovered metric is arithmetic over two values read directly from the source row.

## 13. Runtime Artifact Boundary

The local ACME analysis JSON, gold label, and validation report stay under
`research/python/.r11_runtime/` and remain uncommitted:

- `.r11_runtime/analysis/acme_q1_2026_analysis.json`
- `.r11_runtime/gold_labels/acme_q1_2026_gold_label.json`
- `.r11_runtime/gold_labels/acme_q1_2026_gold_label_validation_report.json`

They are runtime artifacts: not committed, not staged, not checked-in durable gold labels.
The same applies to PDFs under `.r10_runtime/`, manifests, and `.pytest_tmp_*` folders.

This closeout document is the only checked-in artifact of R11.15B. It contains no runtime
JSON payloads and no local PDF contents.

## 14. Updated Local Gold-Label Matrix

Clean scorecard cases:

- `COMB.N0000`
- `SAMP.N0000`
- `AEL.N0000`
- `DIMO.N0000`
- `WATA.N0000`
- `LDEV.N0000`
- `ACME.N0000` — new

Manual-review scorecard cases:

- `RENU.N0000`
- `WIND.N0000`

OCR deferred cases:

- `GLAS.N0000`
- `LALU.N0000`

## 15. Recommended Next Step

Re-run the remaining R11.15A candidates — `CITH.N0000`, `CITW.N0000`, `HVA.N0000`,
`REEF.N0000` — against the `a09db00` code before opening any new diagnosis. Split percent
cells are a pypdf artifact, not an ACME artifact, so patch (a) may have moved one or more of
them without a filing-specific fix. `RWSL.N0000` remains a `PARSE_GAP` and should be
diagnosed separately.

The six-column quarter/annual percent map from section 10 is the natural follow-on if a
reported-percent cross-check is wanted across the four-value cases. It should be scoped as
its own task with its own blast-radius measurement, not attached to a candidate rerun.
