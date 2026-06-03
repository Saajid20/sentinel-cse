# R10 Candidate Context Adapter Design

## Purpose

This document defines the future adapter that will convert a validated `CandidateContextRequest` into R10 retrieval and query intent for source-bound context and risk review.

The adapter is a bridge from technical candidate evidence into R10 research workflow preparation. It is not:

- R10 execution
- R11 execution
- strategy logic
- a trading recommendation

Its role is to prepare safe, auditable inputs for later R10 review without claiming source evidence or policy outcomes on its own.

## Non-goals

- No live trading.
- No order execution.
- No buy/sell/hold decisions.
- No strategy threshold changes.
- No automatic promotion from technical candidate to action.
- No R10 output without source documents.
- No R11 financial inference from technical evidence.
- No network calls in dry-run phases.

## Current Bridge Input

The current upstream bridge artifact is `CandidateContextRequest`, produced from the technical candidate dossier flow.

Fields currently useful to R10:

- `ticker`
- `company_name`
- `evidence_tier`
- `review_status`
- `technical_summary.total_filtered_count`
- `technical_summary.first_session`
- `technical_summary.last_session`
- `warnings`
- `requested_reviews`
- `artifact_refs.runtime_root`
- `artifact_refs.session_stems`

These fields can help explain why context review is being requested and which runtime artifacts support the request.

The following fields should be treated only as context hints, not as source evidence:

- `baseline_count`
- `diagnostic_count`
- `variants_seen`
- technical metrics
- session/replay evidence

R10 may use those values to prioritize or describe review scope, but it must not treat them as disclosure facts, macro evidence, or fundamentals evidence.

## Existing R10 Contracts To Reuse

Future implementation should reuse existing R10 contracts and flow wherever possible:

- `DocumentQuery` if applicable
- `RetrievedContextAnalyzer`
- `ContextAgent`
- `CseNewsAnalysis`
- `R10AnalysisReport`
- `R10PolicyDecision`

The adapter should feed into that existing stack rather than introduce a parallel R10 report type. A new R10-side schema should only be added later if a real gap is proven.

## R10 Adapter Responsibility

The adapter should produce retrieval intent, not source claims.

Expected responsibilities:

- validate `CandidateContextRequest` first
- extract ticker and company identity
- create query terms
- select requested R10 source categories
- attach candidate artifact references
- preserve safety assertions
- prepare a dry-run query plan for later R10 retrieval

The adapter should not:

- call R10 in this phase
- call network
- treat the technical dossier as a source document
- infer fundamentals from technical evidence
- output `SUPPORT`, `BLOCK`, `MANUAL_REVIEW`, or `NO_EFFECT` itself unless those labels are later produced by actual R10 analysis

## Source Selection Rules

Primary source intent:

- CSE announcements/disclosures for ticker
- CSE announcements/disclosures for company name
- CSE financial announcement/disclosure metadata where available

Optional source intent:

- CBSL macro context only when macro or market context is explicitly relevant
- do not query CBSL by default for every ticker unless the request or broader market context warrants it

The adapter outputs retrieval intent only. Actual evidence must come from R10-controlled source documents and metadata.

## Proposed Future `R10CandidateContextReviewRequest` Shape

This is a draft future shape for design discussion only. It is not a current runtime contract and should not be implemented in this phase.

```json
{
  "schema_version": "r10-candidate-context-review-request/draft-v1",
  "candidate_request_ref": {
    "schema_version": "candidate-context-request/v0.1",
    "ticker": "PKME.N0000",
    "artifact_path": ".runtime-pipeline/candidate-context-requests/PKME.N0000.json"
  },
  "ticker": "PKME.N0000",
  "company_name": "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
  "evidence_tier": "Tier A",
  "review_status": "MANUAL_REVIEW",
  "technical_summary": {
    "total_filtered_count": 6,
    "first_session": "atrad-session-20260602-040121",
    "last_session": "atrad-session-20260602-042010"
  },
  "requested_source_types": [
    "CSE_DISCLOSURE",
    "CSE_ANNOUNCEMENT",
    "CSE_FINANCIAL_DISCLOSURE",
    "CBSL_CONTEXT"
  ],
  "query_terms": [
    "PKME.N0000",
    "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
    "DIGITAL MOBILITY SOLUTIONS",
    "PKME"
  ],
  "required_validations": [
    "candidate_context_request_validated",
    "source_documents_required",
    "r10_output_schema_validated",
    "source_citation_required"
  ],
  "artifact_refs": {
    "runtime_root": ".runtime-pipeline/multi-session-validation",
    "session_stems": [
      "atrad-session-20260602-040121",
      "atrad-session-20260602-042010"
    ]
  },
  "safety": {
    "research_only": true,
    "context_risk_only": true,
    "not_financial_advice": true,
    "not_live_execution_guidance": true,
    "human_review_required": true
  }
}
```

This draft shape is intentionally narrow. It exists to describe the future adapter boundary, not to freeze an implementation contract.

## R10 Expected Output Boundary

R10 output must remain aligned with existing R10 artifacts:

- `CseNewsAnalysis`
- `R10AnalysisReport`
- `R10PolicyDecision`

Allowed policy labels remain:

- `SUPPORT`
- `BLOCK`
- `MANUAL_REVIEW`
- `NO_EFFECT`

The adapter must not introduce buy/sell/hold labels or any other trading-action framing.

## Dry-run CLI Concept For Later Phase

Potential future script:

- `research/python/scripts/build_r10_candidate_context_request.py`

Expected future dry-run behavior:

- accept `--input` CandidateContextRequest JSON
- validate input
- print proposed query terms
- print source type intent
- print safety note
- perform no R10 execution
- perform no network calls
- write no output file unless a later phase explicitly approves that behavior

This dry-run CLI would exist to make adapter behavior inspectable before any retrieval integration is introduced.

## Safety Boundaries

- Technical evidence is not source evidence.
- R10 must retrieve actual CSE/CBSL documents.
- Every R10 output must cite source documents.
- LLM outputs must remain schema validated.
- No automatic action promotion.
- Human review required.
- Runtime artifacts should not be committed.
- No trading-action language.

Additional boundary rules:

- Candidate evidence can explain review priority, but it cannot substitute for CSE/CBSL documents.
- R10 remains context/risk only.
- R10 should not treat technical evidence as proof of fundamentals, disclosures, or company events.

## Implementation Stages

- Stage A: docs-only adapter design
- Stage B: dry-run CLI query-plan builder
- Stage C: optional schema if dry-run contract stabilizes
- Stage D: R10 retrieval integration using local/source-bound documents
- Stage E: R10 report attachment to candidate manual review packet

The intended progression is conservative. The adapter should become explicit and auditable before any execution path is added.
