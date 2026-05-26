# Sentinel-CSE R11 Table Extraction Bakeoff

## 1. Purpose

R11 must evaluate table extraction tools on real CSE financial PDFs before adopting any heavy dependency or OCR API. The bakeoff is a controlled way to compare parser quality, setup cost, repeatability, privacy risk, and fit with the R11 schema layer.

The goal is to choose the first practical extraction path for CSE financial disclosures while preserving the R11 principle: "LLM reasons. Python calculates. Schemas enforce. R10 supplies truth."

## 2. Why pypdf Text Is Not Enough

Plain PDF text extraction is useful as a baseline, but financial analysis needs more than line-by-line text. R11 needs:

- row labels
- columns/periods
- numeric values
- units
- signs
- footnotes
- source page/table traceability

If table structure is lost, revenue, profit, assets, deposits, impairments, and ratios can be attached to the wrong period or row. That would break source traceability and make downstream normalization/calculation unsafe.

## 3. Candidate Tools

- `pypdf` baseline: existing lightweight PDF text extraction path already used in R10. Concern: does not preserve complex table structure reliably.
- Camelot: local parser for text-based PDF tables. Concern: depends on PDF text quality and may require setup work; scanned PDFs are out of scope.
- Docling: local/open-source document conversion and structure extraction candidate. Concern: dependency complexity and CSE PDF performance are still unknown.
- unstructured.io: document partitioning and structured element extraction candidate. Concern: heavier dependency surface, possible OCR/model requirements, and API/cost risk depending on configuration.
- Mistral OCR: API-based OCR/document understanding candidate that may preserve tables as Markdown/HTML. Concern: network dependency, cost, privacy, rate limits, and vendor lock-in.
- future XBRL/iXBRL adapter: structured reporting parser if CSE filings become available in XBRL/iXBRL. Concern: availability and timeline are uncertain.

## 4. Fixture Document Plan

The initial fixture set should stay small and representative:

- one banking financial review PDF, for example Commercial Bank / `COMB` financial review from prior R10 testing
- one non-bank CSE interim financial statement
- one annual report or larger PDF later
- one difficult PDF if available, for example scanned or table-heavy

Fixtures should be stored under ignored runtime paths such as:

```text
research/python/.r11_runtime/table_bakeoff/fixtures/
```

Do not commit large PDFs to git unless intentionally creating tiny test fixtures.

## 5. Expected Output Shape

Bakeoff output should be judged against the R11.1 schema language. A successful extractor should produce data that can be converted into `ExtractedFinancialTable` with:

- `SourceTrace`
- `statement_type`
- `page_number`
- `columns`
- `rows`
- `extraction_method`
- `extraction_confidence`

The output does not need to be production-perfect during the bakeoff, but it must preserve enough structure to support future `NormalizedFinancialStatement` conversion.

## 6. Scoring Rubric

Score each candidate from 0 to 5 for:

- table detection
- row-label accuracy
- column/period accuracy
- numeric fidelity
- unit/sign preservation
- page/source traceability
- repeatability
- speed
- setup complexity
- local/offline feasibility
- cost/privacy risk

Suggested interpretation:

- 0: unusable or not evaluated
- 1: detects fragments but cannot support R11
- 2: useful only for narrow manual inspection
- 3: workable for selected PDFs with manual review
- 4: strong candidate with manageable caveats
- 5: reliable default for the tested fixture class

## 7. Acceptance Criteria

A tool should be accepted only if:

- it preserves core financial statement tables
- numeric values remain aligned to correct periods
- output can be converted into `ExtractedFinancialTable`
- it works on Windows or has a practical workflow
- tests can run without live network calls

## 8. Rejection Criteria

Reject or postpone tools if:

- they require too much setup for little gain
- they corrupt numeric alignment
- they cannot preserve tables
- they require network/API for normal tests
- privacy/cost is unacceptable

## 9. Bakeoff Process

1. Select fixture PDFs from R10 verified CSE documents.
2. Run `pypdf` baseline.
3. Run Camelot on text-based PDFs.
4. Run Docling.
5. Run unstructured.io.
6. Run Mistral OCR only manually/API-gated.
7. Compare outputs using rubric.
8. Pick first adapter to implement.

## 10. Manual vs Automated Evaluation

The initial evaluation can be manual. That is acceptable because the first goal is to understand whether each tool preserves CSE financial tables well enough to justify implementation.

Later scoring can become structured JSON, with one record per tool/document/table. `pytest` should use small local fixtures and fake outputs where needed. No network calls should run in `pytest`.

## 11. Relationship to XBRL/iXBRL

If CSE provides XBRL/iXBRL financial statements later, R11 should prefer structured XBRL parsing over PDF OCR when available. Structured filings should reduce parser ambiguity, improve line-item traceability, and make audit trails easier to validate.

## 12. Immediate Next Implementation Step

R11.3B should implement a `pypdf` baseline extraction adapter or local fixture inspection script using existing dependencies only.

That step should remain local, deterministic, and fixture-based. It should not add OCR dependencies or API calls.

R11.3B is now started/completed with the initial `pypdf` baseline adapter under `research/python/sentinel_research/agents/r11/extraction/`.

R11.3E is now started/completed with a deterministic statement page locator for `pypdf` baseline outputs under `research/python/sentinel_research/agents/r11/extraction/statement_locator.py`.

R11.3F is now started/completed with a prototype `pypdf` financial row parser under `research/python/sentinel_research/agents/r11/extraction/pypdf_row_parser.py`.

## 13. Safety Boundary

- no trading recommendations
- no broker/execution integration
- no random web browsing
- no live OCR/API calls in tests
- no expansion beyond R10 verified source boundary

The bakeoff is an extraction evaluation design. It does not authorize new live sources, trading actions, or autonomous browsing.
