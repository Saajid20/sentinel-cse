# Sentinel-CSE R11 Architecture

Institutional Financial Analyst Layer

## Purpose

R11 is the Sentinel-CSE Institutional Financial Analyst layer. It extends the completed R10 foundation by turning verified official corporate disclosures into traceable financial analysis dossiers.

R10 establishes the verified document boundary. R11 operates inside that boundary to extract financial tables, normalize accounting line items, run deterministic Python calculations, and use an LLM only for analyst reasoning and interpretation. R11 is documentation-first at R11.0A; schemas, extraction code, calculation tools, and provider workflows are planned later.

## Relationship with R10

R10 is the curator, verifier, and boundary creator for official source material. It ingests and stores controlled CBSL/CSE documents, records source metadata, supports retrieval, and produces context-oriented analysis and simulation-only policy decisions.

R11 is the financial analyst layer. It consumes R10-verified raw `SourceDocument` records, local PDFs when available, and source metadata such as ticker, company, announcement identifiers, announcement types, and source URLs. R11 may use `R10AnalysisReport` as supporting context and may consider `R10PolicyDecision` as optional context when explaining broader risk posture.

R11 should not depend only on R10 summaries. Financial analysis needs raw tables, statement labels, periods, footnotes, and source pages. Summaries can help prioritize attention, but they are not sufficient evidence for normalized financial statements or calculated metrics.

## Confirmed Source Boundary

CBSL and CSE are the only confirmed source families now.

R11 corporate analysis should use the CSE Announcements feed as the official firehose for listed-company disclosures. CSE announcement metadata and downloaded disclosure PDFs are the initial corporate disclosure boundary.

Future sources are not finalized. Daily FT or other news sources must not be assumed. Any additional source family must be added later through explicit source curation and source adapters.

## Core Design Principle

"LLM reasons. Python calculates. Schemas enforce. R10 supplies truth."

LLM reasons: the model identifies material changes, explains context, compares management commentary with reported results, and writes analyst interpretation.

Python calculates: all numeric ratios, growth rates, margins, changes, and score inputs are computed by deterministic Python tools, not mentally by the LLM.

Schemas enforce: strict Pydantic schemas define accepted inputs, outputs, audit records, source traces, metric shapes, and unsafe-language rejection.

R10 supplies truth: R11 uses R10-verified official documents, local PDF artifacts, and source metadata as the evidence boundary.

## High-Level Pipeline

```text
CSE Announcement PDF
-> R10 SourceDocument
-> R11 table extraction
-> ExtractedFinancialTable
-> financial table normalization
-> NormalizedFinancialStatement
-> Python calculation toolbox
-> ToolAuditEntry
-> LLM analyst interpretation
-> R11AnalystDossier JSON
```

## R11 Inputs

- R10 `SourceDocument`
- Original or local PDF path when available
- CSE metadata: ticker, company, announcement_id, announcement_type, source URL
- `R10AnalysisReport` as context
- `R10PolicyDecision` as optional context

## R11 Outputs

`R11AnalystDossier` is the strict JSON output for an institutional analyst review. It should preserve the raw evidence boundary, extracted financial facts, calculated metrics, analyst interpretation, red flags, and auditability.

Planned output structures include:

- `R11AnalystDossier`: top-level validated dossier for one company disclosure or analysis bundle.
- `FundamentalScorecard`: structured non-trading assessment of financial quality, trend strength, balance-sheet risk, disclosure quality, and accounting risk.
- `FinancialMetric`: deterministic numeric metric with value, units, period, formula identity, and source references.
- `AccountingRedFlag`: traceable concern such as margin compression, unusual impairment movement, leverage deterioration, or inconsistent line-item presentation.
- `ToolAuditEntry`: calculation or extraction audit record containing tool name, version, inputs, outputs, timestamps, and source references.
- `SourceTrace`: source document, page/table/row/column reference, quote or value pointer, and source metadata.

## Table Extraction Strategy

Plain `pypdf` text extraction is not enough for financial statements. Annual and interim reports often contain multi-column statements, merged cells, footnotes, scanned pages, rotated tables, inconsistent spacing, and sector-specific formats. Losing table structure can corrupt periods, labels, signs, and units.

Candidate table extraction tools to evaluate:

- `pypdf` baseline
- Camelot
- Docling
- unstructured.io
- Mistral OCR
- future XBRL/iXBRL adapter

R11 should run a table extraction bakeoff before committing to one parser. The bakeoff should use local CSE disclosure fixtures, compare table structure preservation, period alignment, numeric fidelity, page references, speed, dependency cost, and offline reproducibility.

See `research/python/docs/r11_table_extraction_bakeoff.md` for the R11.3A bakeoff design.

## Accounting / Line-Item Normalization

Financial disclosures use inconsistent labels across companies, sectors, and reporting periods. R11 needs a normalization layer that maps disclosure labels into canonical internal fields while preserving the original label and source trace.

Initial examples:

- Turnover -> `revenue`
- Net Interest Income -> `net_interest_income`
- Profit after taxation -> `profit_after_tax`
- Impairment charges -> `impairment_charges`
- Customer deposits -> `deposits`
- Total assets -> `total_assets`

SLFRS/CSE-specific aliases will grow over time. Normalization should be auditable, sector-aware where necessary, and reversible enough that reviewers can inspect the original disclosure language.

## Python Calculation Toolbox

Initial deterministic calculations:

- `yoy_growth`
- `ratio`
- `margin`
- `margin_change_pp`
- `gross_margin`
- `net_interest_margin`
- `cost_to_income_ratio`
- `debt_to_equity`
- `impairment_change`

No calculated metric enters the dossier unless it has a `ToolAuditEntry`.

## Agentic Workflow

R11 uses a controlled agentic flow:

- The LLM reads verified extracted tables and calculated metrics.
- The LLM identifies what matters and which additional deterministic calculations are needed.
- Python tools calculate metrics from normalized statement data.
- The LLM interprets the audited metrics and source traces.
- Pydantic validates the final `R11AnalystDossier`.
- Unsafe trading language is rejected.

R11 is not an autonomous browsing agent. It must not browse random websites, scrape company websites, or expand the evidence set outside confirmed source adapters.

## Existing Repos / Datasets To Reuse

Evaluation and reference resources:

- FinQA
- TAT-QA
- DocFinQA
- FinGPT
- PIXIU / FinMA
- FinanceToolkit
- financial-ratios packages
- OpenBB as architecture reference only

These are not live Sentinel-CSE sources. They may inform evaluation design, metric definitions, prompt structure, data modeling, or benchmark methodology, but they do not expand the production source boundary.

See `research/python/docs/r11_tools_datasets_matrix.md` for the R11.0B tools and datasets evaluation matrix.

See `research/python/docs/r11_teaching_from_finance_resources.md` for the R11.0C teaching strategy from external finance resources.

## Safety Boundary

Forbidden behavior:

- no buy/sell/hold/order output
- no broker/ATrad/session/execution imports
- no live technical-engine integration
- no random browsing
- no invented numbers
- no unaudited calculations

R11 must not place orders, recommend trading actions, modify strategy thresholds, or connect to broker, ATrad, session, execution, order, strategy, dashboard, or live technical-engine code.

## Implementation Roadmap

- R11.1 schema foundation is now started/completed with the initial strict Pydantic dossier, table, metric, scorecard, red-flag, audit, and source-trace models under `research/python/sentinel_research/agents/r11/`.
- R11.2 calculation toolbox is now started/completed with deterministic pure-Python ratio, growth, margin, leverage, impairment, rounding, and direction helpers under `research/python/sentinel_research/agents/r11/tools/`.
- R11.3A table extraction bakeoff design is now started/completed in `research/python/docs/r11_table_extraction_bakeoff.md`.
- R11.3B `pypdf` baseline extraction adapter is now started/completed under `research/python/sentinel_research/agents/r11/extraction/`.
- R11.3E deterministic statement page locator is now started/completed under `research/python/sentinel_research/agents/r11/extraction/statement_locator.py`.
- R11.3F prototype `pypdf` financial row parser is now started/completed under `research/python/sentinel_research/agents/r11/extraction/pypdf_row_parser.py`.
- R11.0A Architecture document
- R11.0B Existing tools/datasets evaluation matrix
- R11.1 Schema foundation
- R11.2 Python calculation toolbox
- R11.3 Table extraction bakeoff
- R11.4 Extraction adapter interface
- R11.5 Line-item normalization
- R11.6 Non-LLM scorecard prototype
- R11.7 Tool-using analyst workflow
- R11.8 Evaluation harness
- R11.9 Multi-provider LLM comparison
- R11.10 Future training decision

## Testing Strategy

R11 should start with pure unit tests. `pytest` must not make LLM calls, network calls, live source calls, or broker/session calls.

Calculation tests must be deterministic and should cover numeric edge cases such as zero denominators, missing values, sign conventions, units, and period alignment. Table extraction tests should use local fixtures. Analyst workflow tests should use fake providers and fixture dossiers.

## Training / Fine-Tuning Decision

Do not train first.

Training or fine-tuning is only considered after schemas, extraction, calculations, and evaluation exist. Until then, improvements should come from better source boundaries, better extraction, better normalization, deterministic calculations, stronger validation, and benchmarked prompts.

## Open Questions

- Which table extraction tool works best on CSE PDFs?
- Will CSE XBRL/iXBRL become available soon enough to reduce PDF parsing need?
- Which metrics should be sector-specific?
- How should R11 combine with R10 policy decisions?
- Which LLM provider performs best for analyst interpretation?

## Close

R11 begins as a controlled financial analysis workflow, not a trained model or autonomous trading agent.
