# R11 Deterministic v0.1 Closeout

## 1. Closeout Decision

R11 deterministic v0.1 is functionally complete for one clean real CSE financial PDF and its end-to-end deterministic analysis path. It is not yet production-complete, and it is not yet broadly validated across many companies, sectors, or difficult disclosure formats.

## 2. Scope

This closeout covers the non-LLM deterministic R11 path only:

- `pypdf` baseline extraction
- statement page classification
- row parsing
- line-item normalization
- semantic value mapping
- Python metric verification
- metric aggregation and deduplication
- `FundamentalScorecard`
- deterministic analysis JSON
- `R11AnalystDossier` JSON

## 3. Proven Real-Document Path

The deterministic path has been validated on a real `COMB.N0000` CSE financial review PDF:

- Input: Commercial Bank Q1 2026 financial review PDF
- Statement pages used: 5-8
- Output: deterministic analysis JSON
- Output: deterministic dossier JSON
- Financial metric count: 14
- Audit entry count: 14
- Red flag count: 0
- `manual_review_required`: `False`

These outputs are local runtime artifacts under `.r11_runtime`. They are not required committed artifacts and are not part of the tracked repository state.

## 4. Architecture Completed

The following deterministic R11 components are now implemented:

- schemas
- calculations
- extraction
- statement locator
- row parser
- line-item mapper
- value mapper
- metric builder
- metric aggregator
- scorecard builder
- dossier builder
- manual inspection script
- manual dossier generation script

## 5. Safety Boundary

R11 deterministic v0.1 remains inside a strict non-trading, non-LLM safety boundary:

- no LLM calls
- no DeepSeek calls
- no network access
- no OCR APIs
- no trading recommendations
- no buy/sell/hold/order language
- no broker/ATrad/session/execution integration
- no live technical-engine integration

## 6. What R11 Can Do Now

R11 can now:

- extract clean text-based CSE financial statements with the `pypdf` baseline
- classify statement pages
- parse financial rows
- normalize key banking line items
- map COMB-style six-column values
- verify reported growth percentages using Python
- preserve an audit trail through `ToolAuditEntry`
- deduplicate duplicate metrics safely
- build a guarded `FundamentalScorecard`
- build a schema-valid `R11AnalystDossier`

## 7. What R11 Cannot Do Yet

R11 deterministic v0.1 cannot yet:

- claim broad validation across many companies or sectors
- reliably handle scanned or image-heavy PDFs
- parse cash-flow statements into deterministic metrics
- rely on a completed Camelot/Docling/OCR bakeoff path
- use a finished dataset teaching or evaluation harness
- provide an LLM analyst layer
- integrate into a dashboard workflow
- expand the source boundary beyond R10-verified documents
- perform automatic production ingestion for R11

## 8. Known Limitations

- `pypdf` works well for the clean COMB PDF but may fail on more complex layouts.
- The current alias map is banking- and COMB-biased.
- The value mapper assumes a COMB-style six-column layout.
- Scorecard rules are prototype heuristics.
- Total liabilities growth is treated conservatively as a risk/deteriorating signal.
- `cash_flow_quality` remains `UNKNOWN`.
- Metric aggregation deduplicates only the scorecard-ready view while preserving raw occurrences.
- Output depends on the selected or shown pages in the manual inspection script.

## 9. Test Status

Latest deterministic R11/R10 test status:

```powershell
python -m pytest research/python/tests -k "r11 or r10"
```

Result: `367 passed, 61 deselected`

A non-blocking pytest cache warning may appear on Windows.

## 10. Runtime Scripts

Key manual deterministic scripts:

- `research/python/scripts/r11_inspect_pypdf_baseline.py`
- `research/python/scripts/r11_generate_dossier_from_analysis.py`

Example 1: generate deterministic analysis JSON from the COMB PDF

```powershell
python research/python/scripts/r11_inspect_pypdf_baseline.py --pdf "research/python/.r10_runtime/cse_disclosures/manual_pdfs/comb_q1_2026_financial_review.pdf" --start-page 5 --end-page 8 --max-lines-per-page 1 --show-scorecard --metric-entity group --output-analysis-json "research/python/.r11_runtime/analysis/comb_q1_2026_deterministic_analysis.json"
```

Example 2: generate dossier JSON from deterministic analysis JSON

```powershell
python research/python/scripts/r11_generate_dossier_from_analysis.py --analysis-json "research/python/.r11_runtime/analysis/comb_q1_2026_deterministic_analysis.json" --ticker "COMB.N0000" --company "Commercial Bank of Ceylon PLC" --title "COMB Q1 2026 Deterministic R11 Dossier" --source-title "Commercial Bank Q1 2026 Financial Review" --source-url "https://cdn.cse.lk/cmt/upload_report_file/369_1778755847521.pdf"
```

## 11. Next Validation Plan

The next validation step should test 2-3 more real CSE PDFs:

- another banking financial review
- one non-bank interim financial statement
- one difficult table-heavy or scanned PDF if available

## 12. Next Build Phases

- R11.8A: evaluation harness foundation
- R11.8B: first FinQA/TAT-QA adapter
- extraction bakeoff expansion if `pypdf` fails
- cash-flow parsing
- scorecard refinement
- later LLM analyst layer only after the deterministic dossier path is stable

## 13. Final Summary

R11 deterministic v0.1 proves Sentinel-CSE can produce a non-LLM, Python-verified financial analysis dossier from a real CSE financial PDF. It is ready for broader validation, not production deployment.
