# R11 Capital Strength Negative-Equity Guard Closeout

## 1. Closeout Decision

`_build_capital_strength` in
`research/python/sentinel_research/agents/r11/analysis/scorecard_builder.py` scored
`capital_strength` from the equity **growth percentage** alone. It never inspected the
sign or the level of equity, so a book-insolvent company could be reported as
capital-strong.

This closeout covers the guard that fixes it. It is deliberately scoped to
`capital_strength`. The sibling audit in section 6 found a second, related live defect in
`_build_balance_sheet_risk`; that one is recorded here and left for a separate task with
its own approved design, not fixed here.

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

`HVA.N0000` is the concrete case. Its group balance sheet carries:

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

## 5. Blast Radius — 15 Local PDFs

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

## 7. The Lesson Worth Preserving

`HVA.N0000` currently reports `capital_strength: None` and
`manual_review_required: true` — but **not** because anything in the scorecard understood
that its equity is negative. It reports that way because
`group_total_equity_growth` fails to extract from its PDF. The only thing standing between
the shipped defect and a misleading `HIGH` on a book-insolvent company was a **broken
parser**.

That inversion is the point. A parsing bug was silently doing the job of a safety control.
The moment the extraction is repaired the defect becomes visible, which is exactly why the
guard had to land **before** the recovery, in its own commit, with the blast radius
measured while the case was still unreachable. Correctness that depends on an unrelated
failure is not correctness; it is a coincidence with an expiry date.

Generalised: when a case looks safe, check whether it is safe *by construction* or safe
*by accident*. Whenever a known defect has no live instance, ask what is suppressing it
before concluding it does not matter.
