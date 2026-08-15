# R10 Local Retrieval Smoke Test Closeout

First end-to-end run of the R10 local retrieval chain against real CSE source documents
for a real ticker (`PKME.N0000`, DIGITAL MOBILITY SOLUTIONS LANKA PLC).

This is a retrieval closeout only. No `ContextAgent`, no analyzer, no LLM, no network, no
policy output and no trading guidance. Retrieved documents are candidate evidence for
human review, nothing more.

## 1. Blocker history

The handoff into this workstream recorded the blocker as "no real PKME source document
available". That framing was wrong.

The root cause was an access-path problem, not a missing company:

- `research/python/scripts/r10_lookup_cse_financial_reports.py --ticker PKME` returned
  0 rows.
- The same script run unfiltered returned 204 rows.

PKME documents exist and were ultimately fetched. The lookup path simply did not reach
them. Once that was understood, four real PKME PDFs were obtained and a local document
store was built.

## 2. Two structural blind spots in R10 source access

This is the most important content in this document. The smoke test succeeded, but it
succeeded over an evidence base that is narrower than it looks.

### 2.1 `getFinancialAnnouncement` appears to be a rolling recent feed, not an archive

**Status: inference, not established fact.**

`CseApiClient.get_financial_reports()`
(`research/python/sentinel_research/agents/ingestion/cse_api.py`) POSTs
`/getFinancialAnnouncement` with an **empty form payload** — no symbol, no date window,
no offset, no page parameter. The response is a single flat list, and
`r10_lookup_cse_financial_reports.py` filters that list client-side.

The observed behaviour is consistent with the endpoint returning a rolling window of
recent filings rather than a historical archive. If that reading is right, historical
interim and annual filings are simply unreachable through this endpoint: there is no
parameter with which to ask for them.

The evidence for this inference is weak and must be treated as such:

- it rests on a 5-row sample out of the 204 rows returned,
- the client sends no pagination or date arguments, so "not returned" and "does not
  exist" cannot be distinguished from the tooling's behaviour alone.

Confirming or refuting this requires a deliberate, separately authorized probe of the
endpoint's parameters. It has not been done.

### 2.2 `getGeneralAnnouncementById` serves only "general" announcements

`CseApiClient.get_announcement_detail()` POSTs `/getGeneralAnnouncementById` and raises
`missing reqBaseAnnouncement object` when the response has no `reqBaseAnnouncement` key.

Probing announcement IDs by hand produced a clean split:

| Outcome | IDs |
|---|---|
| Resolved | 27282, 27278, 29549, 34241, 37354 |
| `missing reqBaseAnnouncement object` | 28300, 37113, 34127, 27686, 27304, 31272 |

The failing IDs correspond to CASH DIVIDEND, CHANGE OF COMPANY NAME,
DEALINGS/RELEVANT INTEREST and ESOS announcements. These are not transient errors and
not malformed IDs. Corporate-action announcement classes live behind an endpoint the
current tooling does not implement.

### 2.3 Consequence — state this plainly

**R10 currently cannot see dividends, company name changes, or any past interim filing.**

Anyone building analysis on this retrieval chain must not assume the evidence base is
complete. An empty R10 result for a corporate action means "R10 cannot reach this class
of announcement", not "no such announcement exists". Absence of evidence here is a
tooling limit, not a finding.

## 3. Smoke test method, and why controls mattered

A store containing only the target company's documents makes the test unfalsifiable:
every document matches, and a retriever that returned everything unconditionally would
look identical to a correct one.

The store was therefore built with deliberate negatives:

- store: `.runtime-pipeline/r10-local-stores/pkme-smoke-test.jsonl`
- 9 documents: 4 real PKME PDFs plus 5 non-PKME controls (JFP x2, HNBF, CITW, CITH)

All 5 controls were excluded by the `meaningful_match` gate in
`SimpleDocumentRetriever.search(...)` — they cleared the `source_types` filter but scored
no keyword, ticker or sector match, so they were dropped rather than returned with a low
score. Retrieval had something to reject, and rejected it.

Query plan used: `.runtime-pipeline/r10-candidate-query-plans/PKME.N0000.json`
(query terms `PKME.N0000`, `PKME`, `DIGITAL MOBILITY SOLUTIONS LANKA PLC`,
`DIGITAL MOBILITY SOLUTIONS LANKA`).

## 4. The rename finding — the bare company-name term is load-bearing

PKME listed as DIGITAL MOBILITY SOLUTIONS LANKA **LIMITED** and later became
DIGITAL MOBILITY SOLUTIONS LANKA **PLC**. The store spans both eras:

| Document | Published | Name form in text |
|---|---|---|
| 8. Final Circular (IPO) | 2024-10-03 | LIMITED |
| 4. Oversubscription Letter (IPO) | 2024-10-03 | LIMITED |
| FY25 Q3 Errata Notice | 2025-02-07 | PLC |
| Circular for Shareholders - AGM | 2026-06-04 | PLC |

Pre-rename documents match only the bare term `DIGITAL MOBILITY SOLUTIONS LANKA`; they
never match `DIGITAL MOBILITY SOLUTIONS LANKA PLC`. That costs them exactly 1.0 relative
to post-rename documents.

The practical consequence: the query plan's bare-name term is load-bearing. Drop it and
PKME's entire pre-listing IPO history falls out of results, because those documents also
score no `PLC` match. The rename is invisible in the query plan itself — nothing in the
plan records that the company had a previous name — so the bare-name term is currently
the only thing keeping pre-rename history reachable.

## 5. The `tickers_hint` scoring defect

### 5.1 Defect

`SimpleDocumentRetriever._build_searchable_text` folded `document.tickers_hint` into the
text that keyword matching searches. `tickers_hint` is an annotation **this system writes
at ingestion**, not source document content.

For every PKME document that carried the hint:

- `keyword:PKME` fired off our own annotation (+1.0)
- `ticker:PKME.N0000` fired off the same annotation (+2.0)
- both then appeared in `matched_reasons` as if they were independent corroboration

3.0 of a 5.25 score was the system scoring its own annotation. This is the CLAUDE.md rule
"internal runtime artifacts are not source evidence" in miniature: the document was being
credited for what we wrote about it.

### 5.2 Fix

Remove `tickers_hint` from `_build_searchable_text` only. Nothing else changed; no scoring
weight was touched.

Ticker matching is unaffected. `_matches_exact_or_text` already checks the hint list
directly (`any(hint.lower() == normalized_value for hint in hints) or normalized_value in
searchable_text`), so exact-hint ticker matching survives on its own, and a ticker that
genuinely appears in document text still matches through the text branch.

### 5.3 Before / after (real runs against the smoke store)

Pre-fix: `.runtime-pipeline/r10-local-retrieval-results/PKME.N0000.json`
Post-fix: `.runtime-pipeline/r10-local-retrieval-results/PKME.N0000-post-fix.json`

| Document | `PKME` in own text | Before | After | Change |
|---|---|---|---|---|
| Circular for Shareholders - AGM | yes | 5.25 | 5.25 | unchanged |
| 8. Final Circular (IPO) | yes | 4.25 | 4.25 | unchanged |
| FY25 Q3 Errata Notice | no | 5.25 | 4.25 | lost `keyword:PKME` |
| 4. Oversubscription Letter (IPO) | no | 4.25 | 3.25 | lost `keyword:PKME` |

`ticker:PKME.N0000` still fires on all four documents. All 4 PKME documents are still
retrieved; all 5 controls are still excluded. Validator result on the post-fix artifact:
PASS, 4 matched documents, safety verified.

The two documents whose scores dropped are exactly the two that never mentioned `PKME`
themselves. Their prior scores were inflated by our own annotation.

### 5.4 `sectors_hint` — reported, deliberately not changed

`sectors_hint` is folded into `_build_searchable_text` by the same line-adjacent code and
is also an annotation this system writes at ingestion, so the pattern looks identical, and
sector matching has the same `_matches_exact_or_text` hint fallback that made the
`tickers_hint` fix safe.

It was **not** changed in this commit, because the identity is not proven on real data:

- all 9 documents in the smoke store have an empty `sectors_hint`,
- the PKME query plan emits no sector terms,

so nothing here exercises the sector path, and no before/after evidence exists of the kind
that justified the `tickers_hint` change. A probe run confirmed only that removing it
breaks no current test — that is not the same as demonstrating the defect.

Left for a separate task, to be decided against a case that actually populates
`sectors_hint`.

## 6. `source_type` did no discriminating work

All 9 store documents have `source_type: CSE_DISCLOSURE`, because both fetch scripts
hardcode it:

- `research/python/scripts/r10_fetch_cse_announcement_pdf.py:273`
- `research/python/scripts/r10_fetch_cse_pdf_url.py:224`

The query plan's three distinct source labels (`CSE_DISCLOSURE`, `CSE_ANNOUNCEMENT`,
`CSE_FINANCIAL_DISCLOSURE`) all map down to the single local `SourceType.CSE_DISCLOSURE`.

So the `+0.25` source-type bonus was a constant added to every surviving document. It
changed no ranking and rejected no control. `source_type:CSE_DISCLOSURE` appearing in
`matched_reasons` should not be read as evidence that the document is of a particular
kind — the type was assigned by the fetcher, not derived from the document.

## 7. Verification performed

- `python -m pytest research/python/tests -q` — 765 passed (baseline 763, plus the 2 new
  regression tests).
- Retrieval re-run via `dry_run_r10_candidate_retrieval.py` against the real store,
  written to the `-post-fix` path so the pre-fix baseline stays intact for comparison.
- `validate_r10_local_retrieval_result.py` on the post-fix artifact: PASS.

New regression tests in `research/python/tests/test_r10_retrieval.py`:

- a ticker present only in `tickers_hint` produces no keyword match
- ticker filtering still matches through the hint path, with `ticker:` as the sole reason

## 8. Safety

- No trading labels, no policy output, no recommendation language.
- No `ContextAgent`, no analyzer, no LLM.
- No network calls; the entire run was against the pre-existing local store.
- No new retrieval features beyond removing the annotation from keyword-searchable text.
- Retrieved documents are candidate evidence for human review only.
- `.runtime-pipeline/` artifacts remain gitignored and untracked.
