# Sentinel-CSE — agent working notes

Local, read-only research infrastructure for the Colombo Stock Exchange (CSE). It turns
disclosures, macro context, financial statements and recorded market-session data into
source-backed evidence for **human** review.

It is not a trading system, and no layer of it may become one.

---

## Absolute safety boundary

Never introduce, in any layer:

- BUY / SELL / HOLD / STRONG BUY / RECOMMENDATION / ENTRY / EXIT / TRADE labels
- automatic trade signals, order placement, or broker actions
- changes to ATrad execution/session logic, broker, strategy, or order code

Research layers use these labels instead:

`SUPPORT` · `BLOCK` · `MANUAL_REVIEW` · `NO_EFFECT` · `INSUFFICIENT_EVIDENCE`
`WATCHLIST_RESEARCH` · `CONTEXT_REVIEW_REQUIRED` · `FUNDAMENTALS_REVIEWED`

Working on a research feature is never a reason to touch live pipeline code.

---

## Evidence rules

These have already caused real problems. They are not stylistic.

1. **Never fabricate a source document.** If a real CSE/CBSL document is missing, the work
   stops and a human supplies it. Mock fixtures are test data and must never stand in as
   evidence for a real ticker.
2. **Internal runtime artifacts are not source evidence.** Candidate dossiers,
   `CandidateContextRequest` files, R10 query plans and runtime diagnostics are outputs of
   this system, not external sources. Never feed one back in as evidence.
3. **Technical evidence is not financial evidence.** A ticker flagged by the session
   pipeline means only "this deserves manual research review".
4. **Never synthesize a missing financial value.** A metric that cannot be recovered stays
   missing and the case becomes `MANUAL_REVIEW`. Guessing is worse than a gap.

---

## Architecture

Three layers, deliberately kept separate. Do not collapse R10 and R11.

| Layer | Owns | Location |
|---|---|---|
| **Session pipeline** | ATrad session recording/replay, technical candidates | `packages/`, `apps/`, `scripts/` |
| **R10** — context/risk | CSE disclosures & announcements, CBSL macro, retrieval | `research/python/sentinel_research/agents/` |
| **R11** — financial analyst | Statement PDFs → metrics → scorecard → dossier | `research/python/sentinel_research/agents/r11/` |

Flow: technical candidate → `CandidateContextRequest` → R10 query plan → local retrieval →
R10 analysis + R11 financial analysis → combined research packet → human review.

**CBSL is not queried for every candidate** — only when an explicit macro-relevance rule
applies. That rule does not exist yet, so CBSL stays deferred.

---

## Extraction philosophy (R11)

The single most important lesson from the recovery sprint:

> Do not solve extraction problems by making the parser more permissive.

Malformed PDF text becomes false financial data that looks legitimate. Real cases hit so
far: unbalanced parens (`(52,2620`), note numbers read as values (`7)`), side-by-side
statements, quarter-vs-annual column blocks, company-vs-group confusion, equity and
segmental rows masquerading as income statement rows.

Fix at the narrowest upstream layer, in this order of preference:

```
page classification → statement-type filtering → layout-specific recovery
→ company/group discrimination → annual-vs-quarter selection
```

Downstream aggregators are usually correct when they report a conflict — the bug is
normally that a bad page was allowed to produce a metric candidate. Prefer deterministic
logic and explicit markers over regex widening. Never reach for an LLM or OCR to paper over
a deterministic parsing bug.

---

## Worktrees

One repo, many worktrees, one workstream each, so parallel agents don't collide.
Verify with `git worktree list` — branches drift.

| Path | Owns |
|---|---|
| `C:\Users\USER\sentinel-cse` | main |
| `C:\Users\USER\sentinel-cse-pipeline` | R10 retrieval / session pipeline |
| `C:\Users\USER\sentinel-cse-r11` | R11 analyst layer |
| `C:\Users\USER\sentinel-cse-r10-source` | R10 source ingestion |
| `C:\Users\USER\sentinel-cse-r10-financial-reports` | R10 CSE report discovery |
| `C:\Users\USER\sentinel-cse-docs-oss` | public docs |

Work in the worktree that owns the workstream. Never run two agents in one worktree.
Stay inside your subtree; if a change seems to require editing another workstream's area,
stop and say so rather than reaching across.

---

## Runtime artifacts — never stage

These directories hold local research output and are gitignored:

```
.runtime-pipeline/              R10 candidate/query/retrieval artifacts
research/python/.r11_runtime/   R11 analysis JSON, gold labels, validation reports
research/python/.r10_runtime/
research/python/.pytest_tmp*/
```

Never `git add -A` or `git add .` — stage named files only. PDFs, analysis JSON, gold
labels, manifests and validation reports stay untracked unless a task explicitly says
otherwise.

---

## Workflow

Inspect before implementing. Do not edit on first contact with a problem.

1. Reproduce and locate the exact failure — source page, extracted text, statement type,
   current mapping behaviour
2. Check whether an existing recovery already handles it (WATA / RENU / LDEV / WIND for R11)
3. Propose the smallest safe change and its blast radius
4. Implement narrowly, with focused regression tests
5. Run targeted tests, then the broader suite
6. Stage named files, commit, push branch, PR

Report back with: files changed · tests run · real-PDF/retrieval rerun result · metrics
recovered · metrics still missing · conflict status · manual-review status · safety
boundary respected · git status · runtime artifacts created.

Never silently expand scope. The repository is the source of truth — do not redesign
settled contracts or schema versions unilaterally.

Network calls (CSE/CBSL fetch, providers, DeepSeek) require explicit per-task
authorization. Never call the network to solve a deterministic local problem.

---

## Commands

Python research suite:

```bash
python -m pytest research/python/tests -q
```

Broader R10/R11 regression subset:

```bash
python -m pytest research/python/tests -k "r11 or r10" -q
```

TypeScript side: `pnpm test` (vitest), `pnpm typecheck`, `pnpm build`.

A `.pytest_cache` permission warning is a known local quirk and does not mean tests failed.

---

## Key paths

R11 extraction and analysis:

```
agents/r11/extraction/pypdf_row_parser.py     strict financial tokenization
agents/r11/extraction/statement_locator.py    statement identification
agents/r11/tables/line_item_mapper.py         row → line item
agents/r11/tables/value_mapper.py             value normalization
agents/r11/analysis/metric_builder.py         metric construction
agents/r11/analysis/metric_aggregator.py      aggregation + conflict detection
agents/r11/analysis/scorecard_builder.py      scorecard
agents/r11/validation/gold_label.py           deterministic gold-label validation
```

(all under `research/python/sentinel_research/`)

R10 and pipeline CLIs live in `research/python/scripts/` — including the candidate context
request builder, R10 query-plan builder, local retrieval dry-run, the validators for each
artifact, and the local document-store bootstrap. Each artifact has a matching validator;
use it rather than eyeballing JSON.

Design and closeout docs are in `research/python/docs/` — read the relevant closeout before
reopening a case that was already recovered.
