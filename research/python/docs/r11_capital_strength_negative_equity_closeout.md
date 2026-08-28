# R11 Capital Strength Negative-Equity Guard Closeout

## 1. Closeout Decision

`_build_capital_strength` in
`research/python/sentinel_research/agents/r11/analysis/scorecard_builder.py` scored
`capital_strength` from the equity **growth percentage** alone. It never inspected the
sign or the level of equity, so a book-insolvent company could be reported as
capital-strong.

This closeout covers two commits, in order:

1. **the guard** - `capital_strength` refuses to score when current equity is `<= 0`
2. **the HVA recovery** - the wrapped balance-sheet label that was hiding HVA's equity

The order is the point, and section 8 explains why. The sibling audit in section 6 found a
second, related live defect in `_build_balance_sheet_risk`; that one is recorded here and
left for a separate task with its own approved design, not fixed here.

## 2. The Defect

The shipped branch logic was:

```python
equity_growth = metric_value(equity_metric)
if equity_growth is None:
    return None
if equity_growth > 5.0:
    return R11ConfidenceLevel.HIGH
if equity_growth >= 0.0:
    return R11ConfidenceLevel.MEDIUM
return R11ConfidenceLevel.LOW
```

`group_total_equity_growth` is a percentage change produced by
`calculate_yoy_growth(current, previous)`, which divides by `abs(previous)`. Because the
denominator is an absolute value, a company whose equity is negative in *both* periods
still produces a well-formed, positive-looking growth number as the deficit narrows.

`HVA.N0000` is the concrete case, and when the guard landed its equity metric did not
extract at all, so the figures below were only visible by reading its balance sheet
directly. Its group balance sheet carries:

| Period | Total assets | Total liabilities | Implied total equity |
|---|---|---|---|
| previous | 1,131,140,945 | 1,201,940,855 | -70,799,910 |
| current | 1,241,119,072 | 1,305,409,748 | -64,290,676 |

That is roughly **+9.2% equity growth** on a company whose liabilities exceed its assets.
Under the old logic `9.2 > 5.0`, so `capital_strength` returned `HIGH` and the scorecard
reported a book-insolvent company as capital-strong.

## 3. Why Growth-Only Reasoning Is Unsound On A Signed Quantity

A growth percentage is a statement about **change**. `capital_strength` is a statement
about **level**. The two are different kinds of claim, and the conversion between them is
only valid while the underlying quantity keeps a fixed sign.

Total assets, total liabilities, revenue and deposits are non-negative by construction, so
growth-to-level reasoning happens to work for them. Total equity is not: it is a residual,
`assets - liabilities`, and it is routinely negative for a distressed issuer. On a signed
residual:

- a narrowing deficit reads as strong positive growth (`-70.8M -> -64.3M` is `+9.2%`)
- a widening surplus and a narrowing deficit are indistinguishable from the percentage
- the percentage carries no information at all about which side of zero the balance is on

The type mismatch is the tell: the scorecard is emitting an `R11ConfidenceLevel` — a level
— from a change-only input.

## 4. The Guard

When the **current** total equity is `<= 0`, `_build_capital_strength` returns `None` and
appends a manual-review reason, which routes the case to `MANUAL_REVIEW` through the
existing `manual_review_reasons` mechanism that `build_scorecard` already uses. No parallel
flag was introduced.

Refusing to score, rather than downgrading to `LOW`:

`R11ConfidenceLevel` has no member that means "this company has negative equity". Returning
`LOW` would leave the case **scored, clean and promotable** — a reader would see `LOW`,
treat it as a completed judgement, and move on without ever learning that equity is
negative. `None` plus a manual-review reason is the only outcome that makes the gap visible
to the human reviewer. This is CLAUDE.md's *"a metric that cannot be recovered stays
missing"* — missing beats wrong — applied one layer higher, at the scorecard.

The threshold is `<= 0`, not `< 0`. Equity of exactly zero is not a scoreable capital
position either.

Data path: the current-period value is read from the selected metric's calculation audit
entry, `selected_audit_entry.inputs["current"]`, via a new `metric_current_value()`
accessor that mirrors the existing `metric_value()`. This is the same path
`research/python/sentinel_research/agents/r11/validation/gold_label.py` already uses
(`_metric_current_value`). Nothing is recomputed, and equity is never derived from other
metrics.

**Unknown is not negative.** If `inputs["current"]` is absent, the guard does not fire and
behaviour is exactly what it was before the guard existed. Guarding on absent data would be
a synthesized judgement in the other direction. In the current 15-PDF corpus this branch is
never taken: `metric_builder` always records `current` and `previous` on the audit entry.

## 5. Blast Radius (Guard) — 15 Local PDFs

Every local PDF in `research/python/.r10_runtime/cse_report_pdfs/` was re-analysed before
and after the guard. **Zero fields changed.**

| PDF | verified / aggregated | capital_strength | manual_review | current equity |
|---|---|---|---|---|
| ael_q1_2026_interim_financials | 3 / 3 | MEDIUM | true | 42,758,661,625 |
| ACME.N0000 | 4 / 4 | HIGH | false | 508,245 |
| CITH.N0000 | 2 / 2 | HIGH | true | 5,761,822,766 |
| CITW.N0000 | 2 / 2 | LOW | true | 2,183,993,897 |
| DIMO.N0000 | 5 / 5 | HIGH | false | 16,860,840 |
| GLAS.N0000 | — | — | — | no extractable text (pre-existing) |
| HVA.N0000 | 3 / 3 | None | true | metric missing |
| LALU.N0000 | — | — | — | no extractable text (pre-existing) |
| LDEV.N0000 | 4 / 4 | HIGH | false | 3,315,426 |
| REEF.N0000 | 2 / 2 | HIGH | true | 5,604,279 |
| RENU.N0000 | 3 / 3 | HIGH | true | 12,485,306 |
| RWSL.N0000 | 1 / 1 | None | true | metric missing |
| WATA.N0000 | 4 / 4 | LOW | false | 3,010,438 |
| WIND.N0000 | 3 / 3 | HIGH | true | 28,931,465,458 |
| samp_q1_2026_interim_financials | 9 / 8 | LOW | false | 171,713,019 |

Every case that currently produces a `capital_strength` has **positive** current equity, so
the guard does not fire anywhere in the existing corpus. No existing clean case (DIMO, AEL,
SAMP, COMB, ACME, WATA, LDEV) changed, and no existing manual-review case changed. The only
case the guard is built for is the one whose equity metric does not extract yet.

Gold-label validation was re-run for all nine labels in
`research/python/.r11_runtime/gold_labels/`. **No status changed**: seven `PASS`
(ACME, AEL, COMB, DIMO, LDEV, SAMP, WATA) and two `MANUAL_REVIEW` (RENU, WIND), identical
before and after. No gold label was edited.

## 6. Sibling Audit

The audit looked for the same class of defect — an `R11ConfidenceLevel` (a level claim)
derived only from growth percentages (change claims) on quantities that can carry a sign.

**`_build_balance_sheet_risk` — same class, confirmed live case, NOT fixed here.**

It computes `growth_gap = liabilities_growth - assets_growth` and buckets on `+/-2.0`. It
never compares the **levels** of assets and liabilities. For `HVA.N0000`, liabilities
(1,305,409,748) exceed assets (1,241,119,072) — the company is book-insolvent — yet the
growth gap is `8.61 - 9.72 = -1.11`, inside the tolerance band, so the function returns
`MEDIUM` balance-sheet risk. This is a real live instance of level-blindness, but the
mechanism differs from the capital-strength defect (a level *relationship* between two
metrics rather than the sign of one), and the correct output is a separate design decision
that the repo owner has not made. Recorded here for a follow-up task; deliberately not
changed, so that the blast radius of this commit stays zero.

**`_build_margin_trend` and `_majority_direction_from_metric_names` — not the same defect.**

These return `MetricDirection`, which is a direction claim, so deriving them from growth
percentages is type-consistent. The signed-base concern is also already handled correctly
downstream: `calculate_yoy_growth` divides by `abs(previous)`, so a loss narrowing from
-405,923 to -462,860 (ACME) still reads `DETERIORATING`, and a swing from -474,771 to
7,100,014 (HVA) still reads `IMPROVING`. No change needed.

**Adjacent observation, not fixed: growth off a negative base.** `ACME.N0000` reports
`group_total_equity_growth = +198.03%` because equity moved from **-518,474** to
**+508,245**. Current equity is positive, so the approved guard correctly does not fire, and
ACME keeps `HIGH`. But that `HIGH` is inflated by a sign flip in the denominator, not by
capital accumulation. Noted for the same follow-up task as `_build_balance_sheet_risk`;
scoring it differently was not part of the approved design.

## 7. HVA Recovery - The Wrapped Balance-Sheet Label

### The gap

`HVA.N0000` produced 3 verified / 3 aggregated metrics with `group_total_equity_growth`
missing. It was not a locator gap: page 5 already classified as `BALANCE_SHEET` with `HIGH`
confidence, and the equity values were present in the extracted text. pypdf wraps the
caption across two lines and puts every value on the **second** one:

```
29: Total Equity attributable to the equity
30: holders of the Company/Total equity (64,290,676)  (70,799,910)  (63,693,376)  (70,245,609)
```

Line 29 carries no numeric token, so `parse_financial_row_text` returned `None` and it was
dropped. Line 30 parsed correctly - all four values recovered, group columns first - but
its label normalised to `holders_of_the_company_total_equity`, which is in no alias map and
names nothing. The metric was never built.

This is the **inverse** of the WIND block recovery. There the label survives and the values
are stranded; here the values survive and the label is cut in half. No existing WATA / RENU
/ LDEV / WIND / ACME recovery covers a wrapped-label layout - ACME's is a split percent
cell, LDEV's and WATA's are column-block selection.

### The fix - a continuation join, not an alias

The recovery joins the label line to its value line and re-parses the combined text. It is
explicitly **not** an alias for `holders of the company total equity`: that string is a
page-layout accident, and aliasing it would make a canonical financial name out of wherever
pypdf happened to break the line. The next issuer wrapping one word earlier would need
another alias, and the one after that another.

`parse_financial_rows_from_table` now joins line `N-1` into line `N` when all of:

- the page's statement type is `BALANCE_SHEET`
- line `N-1` is adjacent, carries no numeric token, and is not a statement or period header
- line `N-1` ends on a word beginning with a **lowercase** letter
- line `N` parses to a row whose label begins with a **lowercase** letter

The last two conditions are the load-bearing ones, and they are deliberately symmetric: a
wrap point is lowercase on both sides of the break. CSE statements title-case their section
headings, so `Equity and Liabilities`, `Non-Current Assets` and `ASSETS` all end on a
capitalised word and are never treated as caption prefixes. Without that test the join
would glue a heading onto the row beneath it - a regression test covers exactly this, and
it caught the weaker first attempt.

A failed re-parse falls back to the unjoined row, so a join can never *remove* a row that
the value line already produced.

Scoping to `BALANCE_SHEET` follows CLAUDE.md's ordering, which puts statement-type
filtering ahead of layout-specific recovery. Income statements in this corpus wrap their
other-comprehensive-income captions the same way (ACME, DIMO, CITH, REEF, WATA, LDEV), and
joining them would produce better labels, but no metric depends on those rows and no case
has been demonstrated for them. They are left alone rather than swept in.

One alias was added, for the issuer's **real** caption, reachable only after the join:
`total equity attributable to the equity holders of the company total equity` maps to
`total_equity`. HVA prints one combined row where a bank prints two, and the slash form
explicitly names total equity. It reconciles against the same page: total equity &
liabilities `1,241,119,072` less total liabilities `1,305,409,748` is the printed
`(64,290,676)`. Nothing was synthesized; every figure is read from the document.

### Outcome

| | before | after |
|---|---|---|
| verified metrics | 3 | **4** |
| aggregated metrics | 3 | **4** |
| `group_total_equity_growth` | missing | present, `+9.19%` |
| current / previous equity | - | -64,290,676 / -70,799,910 |
| `missing_expected_metrics` | `[group_total_equity_growth]` | `[]` |
| conflicts | none | none |
| `capital_strength` | `None` (metric missing) | `None` (**guard fired**) |
| `manual_review_required` | `true` | `true` |

The manual-review reason changed from *"Missing key aggregated metrics"* to:

> Capital strength was not scored: current group total equity is -64290676.0 (<= 0).
> Equity growth of 9.19 percent describes the change, not the negative equity position
> itself.

That is the whole point of the sequencing. **HVA did not become a clean promotion.** It
went from being flagged for a reason that said nothing about its finances, to being flagged
for the reason a human actually needs to see. The source trace records the join:
`pypdf baseline row parser; wrapped label continuation join from line 29`.

### Blast radius - 15 local PDFs, second pass

Re-analysed before and after the join. `HVA.N0000` is the only case whose metrics changed,
and it changed exactly as tabled above.

One other join fires in the corpus: `AEL.N0000` page 9, where
`Share of results of equity-accounted investees, net of` / `tax (Note 8.2 )` rejoins into a
complete caption. It is a segmental note page; neither the old label (`tax_note_8_2`) nor
the new one maps to a canonical metric, so no AEL metric, scorecard field or manual-review
status changed. The join is a strict improvement to the label and a no-op downstream.

Gold-label validation re-run for all nine labels: no status changes. No gold label edited.

## 8. The Lesson Worth Preserving

Before this work `HVA.N0000` reported `capital_strength: None` and
`manual_review_required: true` — but **not** because anything in the scorecard understood
that its equity is negative. It reported that way because `group_total_equity_growth`
failed to extract from its PDF. The only thing standing between the shipped defect and a
misleading `HIGH` on a book-insolvent company was a **broken parser**.

That inversion is the point. A parsing bug was silently doing the job of a safety control.
Repairing the extraction is what makes the defect reachable, which is exactly why the guard
had to land **before** the recovery, in its own commit, with its blast radius measured
while the case was still unreachable. Had the recovery landed first, even by one commit,
HVA would have promoted to 4/4 metrics with `capital_strength: HIGH`, no missing metrics,
no conflicts and `manual_review_required: false` - a clean, promotable and entirely wrong
scorecard on a book-insolvent company. Correctness that depends on an unrelated failure is
not correctness; it is a coincidence with an expiry date.

Generalised: when a case looks safe, check whether it is safe *by construction* or safe
*by accident*. Whenever a known defect has no live instance, ask what is suppressing it
before concluding it does not matter - and when the answer turns out to be another bug, fix
them in the order that never leaves a window where both are wrong at once.
