# Sentinel-CSE R10 Closeout

## Scope

R10 is the Sentinel-CSE News / Macro / Company Intelligence Layer.

It is context/risk intelligence only. R10 is not a trading model, does not place orders, and must not output buy/sell/order instructions.

## Confirmed Sources

The confirmed R10 sources are:

- CBSL
- CSE

Additional sources are not finalized. Future sources must be added through source adapters after source curation and explicit approval.

## Completed Original Phases

### Phase 1

Phase 1 is complete.

Completed:

- strict `CseNewsAnalysis` schema
- `BaseLLMProvider` abstraction
- `DeepSeekProvider`
- `ContextAgent`
- one repair retry
- source integrity guard
- policy consistency guard

### Phase 2

Phase 2 is complete for controlled CBSL/CSE ingestion.

Completed:

- `SourceDocument`
- `LocalDocumentStore`
- append and upsert/dedup storage paths
- manual text/HTML/JSON ingestion
- `pypdf` local PDF ingestion
- CBSL manual URL source
- CSE announcements API client
- CSE controlled selected-PDF download path

### Phase 3

Phase 3 is complete for RAG over real saved/controlled documents.

Completed:

- `SimpleDocumentRetriever`
- `RetrievedContextAnalyzer`
- real CBSL HTML -> R10 analysis
- real CBSL local PDF -> R10 analysis
- real CSE local disclosure PDF -> R10 analysis
- real CSE API -> selected PDF download -> R10 analysis

### Phase 4

Phase 4 is complete as a simulation-only risk-policy handshake.

Completed:

- `TechnicalSignalCandidate`
- `R10PolicyDecision`
- `evaluate_r10_policy(...)`
- manual policy simulation runner

The Phase 4 handshake remains offline/simulated only:

`technical_signal_candidate + R10_context_json -> SUPPORT / BLOCK / MANUAL_REVIEW / NO_EFFECT`

## Architecture Summary

R10 is organized as a modular local analysis stack:

- schemas:
  `CseNewsAnalysis`, source enums, risk/sentiment/policy enums, and evidence source validation
- providers:
  `BaseLLMProvider` and `DeepSeekProvider`
- orchestration:
  `ContextAgent` with prompt construction, repair retry, source integrity guard, and policy consistency guard
- documents:
  `SourceDocument`, text normalization helpers, and JSONL-backed `LocalDocumentStore`
- ingestion adapters:
  static/manual sources, file/JSON/HTML sources, CBSL URL source, PDF sources, and CSE API client/models
- PDF extraction:
  `pypdf` through `PdfFileDocumentSource`
- retrieval:
  `SimpleDocumentRetriever` and `DocumentQuery`
- RAG analysis:
  `RetrievedContextAnalyzer`
- reports:
  `R10AnalysisReport`, deterministic report IDs, and `LocalReportStore`
- normalization:
  catalyst normalization helpers and shareholder/takeover disclosure alias handling
- policy simulation:
  `TechnicalSignalCandidate`, `R10PolicyDecision`, and `evaluate_r10_policy(...)`

## Manual Runtime Scripts

Main manual R10 scripts:

- `r10_fetch_cbsl_url.py`
  Explicit CBSL URL fetch into local store, with optional R10 analysis.
- `eval_r10_local_pdf.py`
  Manual local PDF ingestion and local RAG smoke test.
- `r10_analyze_cse_disclosure_pdf.py`
  Manual local CSE disclosure PDF ingestion and analysis.
- `r10_lookup_cse_announcements.py`
  Manual CSE announcements API list/detail lookup.
- `r10_fetch_cse_announcement_pdf.py`
  CSE announcement detail lookup, one selected PDF download, local ingestion, and optional R10 analysis.
- `r10_generate_report.py`
  Existing local document store -> validated `R10AnalysisReport`.
- `r10_simulate_policy_decision.py`
  Saved report plus simulated technical candidate -> `R10PolicyDecision`.

Supporting manual evaluation scripts also remain available under `research/python/scripts/eval_r10_*.py`.

## Proven Real-Document Paths

The following paths have been proven manually:

- CBSL real HTML -> R10 analysis
- CBSL real PDF local -> R10 analysis
- CSE local disclosure PDF -> R10 analysis
- CSE API -> selected PDF download -> R10 analysis
- R10 report -> simulated technical candidate -> `R10PolicyDecision`

## Safety Boundary

R10 remains inside the intended research-only boundary:

- no broker imports
- no ATrad/session/execution/order code
- no strategy threshold changes
- no live technical-engine integration
- no DeepSeek calls in `pytest`
- network usage is manual-only
- no crawling or scheduled scraping
- no R11 code

R10 is context/risk intelligence only and must not produce order instructions.

## Test Status

Latest reported R10 test command:

```powershell
python -m pytest research/python/tests -k "r10"
```

Latest reported result:

```text
206 passed, 61 deselected
```

The Windows `.pytest_cache` warning is non-blocking.

## Known Limitations

Current limitations:

- manual-only ingestion
- no scheduler or dashboard integration
- DeepSeek output variability remains possible inside the strict schema
- `reason_codes` remain partly free-form
- `pypdf` is limited for scanned PDFs and table-heavy PDFs
- only CBSL and CSE are confirmed sources
- no R11 table-preserving OCR, accounting schema layer, or quantitative analyst tooling
- no real technical engine integration

## Closeout Decision

R10 is closed as:

`R10 Foundation + Controlled CBSL/CSE Ingestion + Offline Policy Simulation`
