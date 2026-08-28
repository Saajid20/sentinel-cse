# R11.15B Remaining Candidate Triage — CITH, CITW, HVA, REEF

## 1. Headline — Null Result

The four remaining R11.15A candidates were re-run against current `main` (`78beed9`,
which contains the ACME recovery commit `a09db00`).

**Nothing moved. None of the three ACME patches recovered a single additional metric on any
of the four filings.** All four remain `MANUAL_REVIEW_CANDIDATE` with byte-identical
aggregated metrics, conflict flags, occurrence counts and scorecards to the R11.15A run.

No ticker was promoted. No gold label was built. This is a genuine null result and is
recorded as one.

The offsetting value of the rerun is diagnostic: it eliminates the split-percent-cell
hypothesis for all four filings on direct evidence, and the diagnosis work that followed
found one thing that matters more than any of the four recoveries — see section 6.

## 2. Before / After

Prior classification is from
`.r11_runtime/analysis/r11_15a_candidate_classification_report.json`. After is from the
reruns in section 3.

| Ticker | Verified | Aggregated | Conflicts | Manual review | Missing core metrics | Status |
| --- | ---: | ---: | --- | --- | --- | --- |
| `CITH.N0000` | 2 → 2 | 2 → 2 | `false` → `false` | `true` → `true` | profit YoY, total liabilities | **UNCHANGED** |
| `CITW.N0000` | 2 → 2 | 2 → 2 | `false` → `false` | `true` → `true` | profit YoY, total liabilities | **UNCHANGED** |
| `HVA.N0000` | 3 → 3 | 3 → 3 | `false` → `false` | `true` → `true` | total equity | **UNCHANGED** |
| `REEF.N0000` | 2 → 2 | 2 → 2 | `false` → `false` | `true` → `true` | profit YoY, total liabilities | **UNCHANGED** |

No regression. The comparison was made field-by-field, not eyeballed: pages extracted, the
full per-page statement-type and confidence classification list, aggregated metric values,
source-trace raw rows and page numbers, occurrence counts, conflict flags,
`missing_expected_metrics`, `manual_review_reasons`, the full scorecard, and
`metric_build_warnings`. Every field matched the stored R11.15A analysis JSON exactly for
all four tickers.

Recovered metric values, unchanged:

| Ticker | Metric | Value | Source page |
| --- | --- | ---: | ---: |
| `CITH` | `group_total_assets_growth` | `0.15` | 4 |
| `CITH` | `group_total_equity_growth` | `5.1` | 4 |
| `CITW` | `group_total_assets_growth` | `1.48` | 3 |
| `CITW` | `group_total_equity_growth` | `-1.48` | 3 |
| `HVA` | `group_profit_for_the_period_yoy_growth` | `1595.46` | 4 |
| `HVA` | `group_total_assets_growth` | `9.72` | 5 |
| `HVA` | `group_total_liabilities_growth` | `8.61` | 5 |
| `REEF` | `group_total_assets_growth` | `2.18` | 4 |
| `REEF` | `group_total_equity_growth` | `6.57` | 4 |

## 3. Why Each ACME Patch Was Inapplicable

The recommendation in the ACME closeout (section 15) was reasonable: split percent cells are
a pypdf artifact, not an ACME artifact. It simply does not hold for these four filings, and
the reason is measurable rather than inferred.

### Patch (a) — split percent-cell collapse: zero applicable input

Every extracted line of all five PDFs was scanned for a parenthesised percent cell carrying
the pypdf-inserted internal space (`( 63%)`):

| Ticker | Split percent cells |
| --- | ---: |
| `ACME.N0000` | 41 |
| `CITH.N0000` | **0** |
| `CITW.N0000` | **0** |
| `HVA.N0000` | **0** |
| `REEF.N0000` | **0** |

CITH, CITW and REEF do print percent variance columns, but pypdf emits them intact —
`(73%)`, `(101%)`, `(5%)` — so `strip_numeric_tokens_from_label` already handled them
before `a09db00`. HVA publishes no percent column at all.

`_collapse_split_percent_cells` is therefore a provable no-op on all four filings. It is not
that the patch fired and did not help; it never had an input to act on.

### Patch (b) — `"three months ended"` quarter marker: no new gate opened

Quarter and annual header markers found per filing:

| Ticker | Pages with a quarter marker | Marker text | New in patch (b)? |
| --- | --- | --- | --- |
| `CITH` | 2, 3, 7, 8 | `quarter ended` | no — already in the tuple |
| `CITW` | 2, 7 | `quarter ended` | no — already in the tuple |
| `HVA` | none | — | no quarter block published |
| `REEF` | 2, 3, 8 | `quarter ended` | no — already in the tuple |

No page in any of the four filings uses `three months ended`. The quarter-plus-annual gate
already fired on CITH page 2/3, CITW page 2 and REEF page 2/3 before `a09db00`, and it still
does not fire anywhere on HVA. Patch (b) changed no gate outcome.

### Patch (c) — unresolved-annual-column-block guard: no candidate dropped

Guard (c) only removes candidates, so its worst case here would have been a regression. It
produced none: all four outputs are identical. On CITH, CITW and REEF the quarter gate fires,
so the guard is never reached. On HVA no page carries both an annual marker and four-value
income rows behind a closed quarter gate in a way that reaches it.

**Conclusion:** the ACME commit is correctly scoped and did exactly what it was measured to
do. It simply has no purchase on these four filings.

## 4. Task 2 — No Gold Label Built

Task 2 was conditional on a ticker reaching 4/4 core metrics with `has_conflicts: false`,
`manual_review_required: false` and `missing_expected_metrics: []`. No ticker met that
condition, so no gold label was written and the validator was not run.

Nothing was adjusted to manufacture a promotion.

## 5. Diagnosed Gaps

No existing recovery covers any of these pages. All four layout detectors were probed
directly against every relevant page, exactly as the ACME closeout did:

| Detector | CITH 2/3/4 | CITW 2/3 | HVA 4/5/7 | REEF 2/3/4 |
| --- | --- | --- | --- | --- |
| `_table_has_ldev_quarter_year_variance_group_income_layout` | `False` | `False` | `False` | `False` |
| `_table_has_renu_side_by_side_combined_statement` | `False` | `False` | `False` | `False` |
| `_table_has_wind_consolidated_income_block` | `False` | `False` | `False` | `False` |
| `_table_has_wind_consolidated_balance_block` | `False` | `False` | `False` | `False` |

Each remaining gap was reduced to an exact source line and confirmed by an **in-memory
counterfactual** — the candidate change applied to a live module in a throwaway process,
never to a source file — so the proposals below are measured, not predicted.

### 5.1 The shared blocker — `group_total_liabilities_growth` is not in the source

**CITH, CITW and REEF do not publish a total-liabilities row.** Every balance-sheet line
matching `total ... liabilit` across the three filings:

| Ticker | Page | Line |
| --- | ---: | --- |
| `CITH` | 4 | `TOTAL EQUITY & LIABILITIES 10,780,483,228 10,764,798,003 …` |
| `CITW` | 3 | `Total equity and liabilities 5,876,769,456 5,790,940,547` |
| `REEF` | 4 | `Total equity and liabilities 11,155,899 10,918,158 …` |

All three print an unlabelled non-current-liabilities subtotal and an unlabelled
current-liabilities subtotal, then jump straight to total equity and liabilities. There is
no labelled `Total liabilities` row anywhere on the page.

This is a **source-document gap, not a parser gap**. The value could be arrived at as
`total assets − total equity`, but that is a value the issuer did not publish, and computing
it is exactly the synthesis that evidence rule 4 forbids.

**Consequence, and it governs everything below: `CITH`, `CITW` and `REEF` cannot reach a 4/4
clean scorecard from these filings under any parser change.** The best any recovery can do
is take them from 2/4 to 3/4. They stay `MANUAL_REVIEW`. Proposed fix: **none.**

### 5.2 `CITH.N0000` — profit row: alias gap

- **Source page:** 2, `CONSOLIDATED STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME`
- **Statement type:** `INCOME_STATEMENT`, `HIGH` confidence — classification is correct
- **Extracted line 21:**
  `Profit/ (Loss) for the period/ year 44,277,850 164,334,059 (73%) 1,279,284 (142,744,691) (101%)`
- **Current mapping behaviour:** the label strips cleanly to
  `Profit/ (Loss) for the period/ year`; values map correctly to
  `value_1`–`value_4` (quarter current/previous, annual current/previous); the
  quarter-plus-annual gate fires and the group-title check passes. The row then normalizes to
  canonical `profit_loss_for_the_period_year`, which is **absent from `_ALIAS_MAP`**, so it is
  not in `VERIFIED_GROWTH_METRIC_MAP` and `build_growth_metric_for_item` returns `None`
  silently.
- **Root cause:** `_ALIAS_MAP` carries `profit loss for the period` and
  `profit loss for the year` but not the combined
  `profit loss for the period year` that period/year interim filings use.
- **Existing recovery covers it?** No.

**Proposed minimal change:** one alias-map entry,
`"profit loss for the period year": "profit_for_the_period"`.

**Measured effect (counterfactual):** `group_profit_for_the_period_yoy_growth = 100.9`,
computed from the annual pair `1,279,284` / `(142,744,691)`, `occurrence_count: 1`,
`conflict: false`, source page 2 only. Page 3 (the company income statement, same layout,
no `CONSOLIDATED` in its title) is correctly excluded by the group-title check.
CITH goes 2/4 → 3/4. Still `MANUAL_REVIEW` because of 5.1.

### 5.3 `REEF.N0000` — profit row: alias gap **and** group-title marker gap

- **Source page:** 2, `CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME`
- **Statement type:** `INCOME_STATEMENT`, `MEDIUM` confidence
- **Extracted line 21:**
  `Profit/ (Loss) for the period/ year 25,972 149,531 (83%) (142,194) (248,898) (43%)`
- **Current mapping behaviour:** two independent blocks, either of which alone is fatal.
  1. Same alias gap as CITH — canonical `profit_loss_for_the_period_year`.
  2. `_table_has_group_income_statement_title_markers` returns `False`. The title markers are
     `consolidated income statement`, `consolidated statement of profit or loss` and
     `group income statement`. REEF's title is
     `CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME`, which matches none of them. With the
     quarter gate open and the group title check failing, only mixed-page balance items are
     returned and the income candidates are dropped.
- **Existing recovery covers it?** No.

**Proposed minimal change:** the CITH alias entry, **plus** one explicit title marker,
`"consolidated statement of comprehensive income"`, appended to
`_GROUP_INCOME_STATEMENT_TITLE_MARKERS`. This is a marker addition in the established style,
not regex widening.

**Group/company discrimination is preserved and was checked, not assumed.** REEF page 3 is
the company income statement titled `STATEMENT OF COMPREHENSIVE INCOME`. It lacks the word
`CONSOLIDATED`, so the new marker does not match it, and the counterfactual confirms a
single occurrence on page 2 only.

**Measured effect (counterfactual):** `group_profit_for_the_period_yoy_growth = 42.87` from
the annual pair `(142,194)` / `(248,898)`, `occurrence_count: 1`, `conflict: false`, page 2.
REEF goes 2/4 → 3/4 core metrics. Still `MANUAL_REVIEW` because of 5.1.

**Blast radius to note before this is scoped:** opening the group-title gate on REEF page 2
also admits every other mapped row on that page. The counterfactual produced one additional
non-core metric, `group_operating_expenses_growth = 3.69`, from
`Operating expenses (195,998) (159,720) 23% (661,864) (687,244) (4%)` — arithmetically
correct against the annual pair, but it is a new metric that did not exist before and it
would change any gold label written for REEF. The full 15-PDF blast radius of the new title
marker has **not** been measured and must be, before any implementation.

### 5.4 `CITW.N0000` — single-entity filing, no consolidated statements

- **Source page:** 2, `STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME`
- **Extracted line 18:**
  `Profit/ (Loss) for the period 3,048,732 43,235,680 (93%) (178,251,046) (169,180,298) 5%`
- **Current mapping behaviour:** the label maps **correctly** to canonical
  `profit_for_the_period`, which **is** in `VERIFIED_GROWTH_METRIC_MAP`. The quarter gate
  fires. The candidate is then dropped because
  `_table_has_group_income_statement_title_markers` returns `False`.
- **Root cause, and it is not a bug:** `WASKADUWA BEACH RESORT PLC` publishes no consolidated
  statements. Its balance sheet on page 3 has a **single** two-value column pair, there is no
  investment-in-subsidiary line, and there is no non-controlling-interest row anywhere. There
  is no group. The pipeline is asking for `group_*` metrics from a filing that has no group
  to report, and correctly declines.
- **Existing recovery covers it?** No, and none should.

**Proposed minimal change: none at the parser layer.** Neither the CITH alias nor the REEF
title marker moves CITW — both counterfactuals were run against it and it stayed at 2/4.

Making CITW recoverable would require a deliberate single-entity determination that treats
company scope as group scope for filings that publish no consolidated statements. That is a
**scope and policy decision, not an extraction fix**, and it carries real risk: the title
this would have to accept, `STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME`, is
character-for-character the title of CITH page 3 and structurally the same as REEF page 3 —
both of which are **company** pages inside group filings that must stay excluded. Any such
rule must therefore key on the absence of consolidated statements across the whole document,
never on a page title.

**Recommendation:** leave CITW as `MANUAL_REVIEW`. It is blocked by 5.1 regardless.

### 5.5 `HVA.N0000` — wrapped equity label, and a scorecard hazard behind it

- **Source page:** 5, `Statement of Financial Position`
- **Statement type:** `BALANCE_SHEET`, `HIGH` confidence
- **Extracted lines 29–30:**
  ```
  29| Total Equity attributable to the equity
  30| holders of the Company/Total equity (64,290,676)   (70,799,910)   (63,693,376)   (70,245,609)
  ```
- **Current mapping behaviour:** pypdf wraps the label across two lines and puts all four
  values on the second. Line 29 has no values and produces no row. Line 30 yields the label
  fragment `holders of the Company/Total equity` → canonical
  `holders_of_the_company_total_equity`, absent from `_ALIAS_MAP` and from
  `VERIFIED_GROWTH_METRIC_MAP`. The values themselves are mapped correctly:
  `value_1`/`value_2` are the group column pair.
- **Existing recovery covers it?** No. This is superficially the WIND class (label and values
  split across extracted lines) but structurally inverted: WIND's recovery handles a label
  line followed by a value line; HVA has a **label continuation** whose tail shares a line
  with the values. `_table_has_wind_consolidated_balance_block` returns `False` on this page.
- **Note on the other three metrics:** HVA is the only one of the four that *does* publish a
  labelled `Total liabilities` row (page 5 line 45), which is why it already has 3/4.

**Do not implement a fix for this yet.** The counterfactual that closes the gap also exposes
a defect that is more serious than the gap — see section 6.

If it is implemented later, the change should be a **deterministic balance-sheet label
continuation join** (a value-less line immediately preceding a valued line on the same
statement page is prepended to that line's label), plus whatever alias the joined label then
requires. It should **not** be a bare alias entry for
`holders of the company total equity`: that string is a pypdf wrap artifact, not a published
line item, and putting it in `_ALIAS_MAP` would bake an extraction accident into the semantic
layer. A continuation join has a wide blast radius across all 15 local PDFs and needs its own
measurement.

## 6. Safety Finding — Negative Equity Is Scored As HIGH Capital Strength

This was found while measuring the HVA counterfactual and is the most consequential result
in this triage.

HVA's total equity is **negative in both periods**: `-64,290,676` current against
`-70,799,910` previous. The company has negative net assets and reports
`Net Assets per Share - (LKR) (0.26)` on the same page.

With the equity metric recovered, HVA reaches 4/4 core metrics,
`has_conflicts: false`, `missing_expected_metrics: []`,
`manual_review_required: false` — a fully clean scorecard, promotable under the clean-case
pattern. And that clean scorecard reads:

```
group_total_equity_growth = 9.19
capital_strength          = HIGH
```

`_build_capital_strength` (`scorecard_builder.py:297`) branches on the growth percentage
alone:

```python
if equity_growth > 5.0:
    return R11ConfidenceLevel.HIGH
```

It never inspects the sign or the level of equity. A company whose equity moved from
`-70.8m` to `-64.3m` is less insolvent than it was; it is not strongly capitalised. The
arithmetic is correct and the conclusion is false.

This is the ACME lesson repeating at the scorecard layer rather than the parser layer, and it
is worse in one respect: on ACME the false value was caught incidentally by a conflict. Here
nothing raises a conflict, nothing raises a warning, `manual_review_required` is `false`, and
the source trace points at a real row on a real page of a real filing. A human reading the
dossier would see `capital_strength: HIGH` next to three other correct metrics.

**HVA's missing equity metric is currently the only thing preventing a materially misleading
scorecard from being published.** Recovering it without a guard would make HVA worse, not
better.

**Recommended sequencing — the guard first, the recovery second:**

1. Add a negative-equity guard to `_build_capital_strength`: when the underlying equity level
   is negative in either period, capital strength must not be `HIGH`/`MEDIUM` on the strength
   of a growth percentage. The case belongs in `MANUAL_REVIEW`.
2. Only then consider the HVA label-continuation recovery in 5.5.

Doing (2) before (1) ships the false signal.

This affects `scorecard_builder.py`, which no R11.15A/B task has touched, and it is a
behaviour change for any future filing with negative equity. It should be scoped as its own
task with its own blast-radius measurement across all 15 local PDFs. It is **not**
implemented here.

## 7. Recommended Scope for the Next Task

In priority order:

1. **Negative-equity guard in `_build_capital_strength`** (section 6). Highest priority. It
   is a correctness defect that exists in shipped code today, independent of these four
   candidates.
2. **`_ALIAS_MAP` entry `profit loss for the period year`** (section 5.2). Smallest, safest,
   best-evidenced change. Moves CITH to 3/4 and is a prerequisite for REEF.
3. **HVA balance-sheet label continuation join** (section 5.5), only after (1).
4. **`consolidated statement of comprehensive income` title marker** (section 5.3), only with
   a full 15-PDF blast-radius measurement, because it admits additional non-core metrics.

Explicitly **not** recommended:

- Any derivation of total liabilities from assets minus equity, for CITH, CITW or REEF. That
  is value synthesis.
- Any single-entity group-scope substitution for CITW driven by a page title.

No change in this list makes any of CITH, CITW or REEF clean. Only HVA is reachable, and only
behind the guard in (1).

## 8. Boundaries Observed

- No network call, no OCR, no LLM. All work was local and deterministic.
- No extraction, mapping, analysis or scorecard source file was modified. The working tree is
  identical to `78beed9`; the counterfactuals in section 5 patched live module objects inside
  throwaway processes and were never written to disk.
- No financial value was synthesized. Every figure quoted is read directly from an extracted
  source row, or is arithmetic over two such rows.
- No trading label of any kind appears in this document or in any artifact produced by it.
  All four tickers remain `MANUAL_REVIEW`.

## 9. Test Result

```
python -m pytest research/python/tests -q
768 passed
```

**Discrepancy noted for the record, not corrected.** The task brief stated a baseline of 766
passed at `78beed9`. The measured count at `78beed9` with a verifiably clean working tree
(`git status --porcelain` empty, `git diff 78beed9 --stat` empty) is **768**. Nothing in this
task added or modified a test. The 766 figure appears to be stale. It is reported rather than
reconciled, since reconciling it by changing anything here would be the wrong move.

## 10. Runtime Artifacts

The reruns wrote four analysis JSON files under `research/python/.r11_runtime/analysis/`:

- `cith_r11_15b_rerun_analysis.json`
- `citw_r11_15b_rerun_analysis.json`
- `hva_r11_15b_rerun_analysis.json`
- `reef_r11_15b_rerun_analysis.json`

These are runtime artifacts. They are gitignored, untracked and unstaged, and they are not
source evidence. No gold label and no validation report was produced, because no candidate
qualified.

This document is the only checked-in artifact of the triage. It contains no runtime JSON
payloads and no local PDF contents beyond the individual statement rows quoted as evidence.
