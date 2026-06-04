# R10 Local Retrieval Dry-Run Design

## Purpose

This document defines how a validated `r10-candidate-query-plan/v0.1` artifact should later map into local R10 document retrieval intent.

This is a local retrieval dry-run design only. It does not execute `ContextAgent`, does not call an LLM, does not perform network ingestion, does not produce policy output, and does not provide trading guidance.

## Non-goals

- No live trading.
- No order execution.
- No buy/sell/hold decisions.
- No strategy threshold changes.
- No new CSE/CBSL fetching.
- No `ContextAgent` execution.
- No `RetrievedContextAnalyzer.analyze(...)` execution.
- No `R10PolicyDecision` generation.
- No R11 analysis.

## Current Inputs

The input artifact for this design is a validated `r10-candidate-query-plan/v0.1` JSON file.

Fields currently relevant to local retrieval are:

- `ticker`
- `company_name`
- `requested_source_types`
- `query_terms`
- `cbsl_context`
- `required_validations`
- `artifact_refs`
- `safety`

These fields describe retrieval intent only. They do not constitute disclosure evidence, fundamentals evidence, or policy evidence.

## Existing Local R10 Retrieval Contracts

Future dry-run retrieval should reuse the existing local R10 retrieval stack:

- `LocalDocumentStore.load_all()`
- `SourceDocument`
- `SourceType`
- `DocumentQuery`
- `SimpleDocumentRetriever.search(...)`

The dry-run should reuse these primitives directly rather than introducing a parallel retrieval stack or a parallel local document format.

## Source Type Mapping

The query-plan source labels are currently more specific than the local `SourceType` enum.

Current mapping for local retrieval should be:

- query-plan `CSE_DISCLOSURE` -> local `SourceType.CSE_DISCLOSURE`
- query-plan `CSE_ANNOUNCEMENT` -> local `SourceType.CSE_DISCLOSURE` for now
- query-plan `CSE_FINANCIAL_DISCLOSURE` -> local `SourceType.CSE_DISCLOSURE` for now
- query-plan `CBSL_CONTEXT` -> local `SourceType.CBSL`

This mapping is necessary because current `SourceType` is coarse. It does not yet distinguish CSE announcements from CSE financial disclosures at the enum level.

The future dry-run should preserve the original requested source labels in its output while querying the mapped local `SourceType` values underneath.

## DocumentQuery Mapping

The validated query plan should map into `DocumentQuery` conservatively:

- `tickers`: use the full ticker from the query plan, for example `PKME.N0000`
- `keywords`: use `query_terms` except the exact full ticker when it is already represented in `tickers`
- `source_types`: use mapped local `SourceType` values
- `limit`: use a deterministic fixed default for the future dry-run, such as `10`
- date filters: defer until the query-plan contract later includes an explicit date window

This keeps the first local dry-run simple and aligned with the current retriever contract.

## Matching Behavior

Expected local matching behavior should follow the current retriever semantics:

- prefer ticker or `tickers_hint` matching when available
- fall back to keyword and document-text matching
- treat company-name matching as lower-confidence because it can be noisy
- make no source claim unless a real `SourceDocument` record is matched

The dry-run should report matched local documents only. It should not infer disclosure meaning or company fundamentals from keyword overlap alone.

## Expected Future Dry-Run Script

The expected future dry-run CLI is:

- `research/python/scripts/dry_run_r10_candidate_retrieval.py`

Expected future behavior:

- accept `--input <r10-candidate-query-plan JSON>`
- validate the query plan first
- load local documents from `LocalDocumentStore`
- build a `DocumentQuery`
- run `SimpleDocumentRetriever.search(...)`
- print matched local documents
- do not call `ContextAgent`
- do not call an LLM
- do not call network
- do not perform new ingestion
- do not produce policy output

## Expected Future Dry-Run Output

The future dry-run output should include:

- query-plan summary
- local `DocumentQuery` summary
- mapped local `SourceType` values
- requested source labels
- query terms used
- matched document count
- top matched local documents
- document id
- source type
- title or source path where available
- score or matched reasons where available
- missing-source warnings
- safety note

This output should remain retrieval-oriented and diagnostic. It should not turn matched documents into policy conclusions.

## Safety Boundaries

- Technical candidate evidence is not source evidence.
- The query plan is retrieval intent only.
- Local documents must be real R10 `SourceDocument` records.
- CSE source types are primary.
- CBSL remains excluded unless the query plan explicitly includes `CBSL_CONTEXT`.
- No source claims without retrieved documents.
- No R10 policy labels produced in the dry-run.
- No trading-action language.
- Human review required.
- Runtime artifacts should not be committed.

## Tests For Future Implementation

Future implementation should add tests for:

- valid query-plan builds deterministic `DocumentQuery`
- default CSE source labels map to `SourceType.CSE_DISCLOSURE`
- `CBSL_CONTEXT` excluded by default
- explicit `CBSL_CONTEXT` maps to `SourceType.CBSL`
- ticker and company keywords map correctly
- empty local store handled clearly
- no matches handled clearly
- matched documents printed deterministically
- no `ContextAgent` call
- no network or ingestion calls
- no files written
- no trading-action language

## Staged Implementation Plan

- Stage A: docs-only design
- Stage B: dry-run CLI using `LocalDocumentStore` and `SimpleDocumentRetriever`
- Stage C: optional JSON export for retrieval dry-run
- Stage D: source-integrity and status reporting
- Stage E: later `ContextAgent` and R10 analysis integration, separately approved
