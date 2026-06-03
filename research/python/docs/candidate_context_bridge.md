# Candidate Context Bridge Design

## Purpose

This document defines the future bridge between technical/offline candidate evidence and the R10/R11 research layers.

The bridge exists to move a candidate from offline technical evidence review into controlled context/risk review, financial statement review, disclosure review, and human review without creating trading recommendations or execution actions.

The bridge is research infrastructure only. It does not authorize live execution, broker integration, or direct action promotion.

## Non-goals

- No live trading.
- No order execution.
- No buy/sell/hold decisions.
- No strategy threshold changes.
- No automatic promotion from candidate to action.
- No LLM direct trading decisions.
- No R11 fundamental inference from technical session evidence alone.

## Current Artifacts

The current technical candidate artifact is produced by `research/python/scripts/candidate_evidence_dossier.py`.

That dossier can be rendered to the terminal and optionally exported to Markdown. It currently summarizes:

- `ticker`
- `company_name`
- `evidence_tier`
- `review_status`
- `total_filtered_count`
- `sessions_seen`
- `strong_full_grid_sessions`
- `partial_coverage_sessions`
- `baseline_count`
- `diagnostic_count`
- `variants_seen`
- `first_session`
- `last_session`
- session evidence
- filtered signal evidence
- blocker context
- warnings
- R10/R11 placeholders

The dossier is technical research evidence only. It is not a disclosure record, not a fundamentals dossier, and not a trading instruction.

## CandidateContextRequest Draft Contract

Future integration should use a dedicated request object that carries candidate evidence into downstream review layers.

This is a draft contract for a future schema phase, not a finalized schema.

Example draft JSON shape:

```json
{
  "schema_version": "candidate_context_request_draft_v1",
  "request_id": "draft-request-id",
  "ticker": "PKME.N0000",
  "company_name": "DIGITAL MOBILITY SOLUTIONS LANKA PLC",
  "generated_from_dossier": true,
  "evidence_tier": "Tier A",
  "review_status": "MANUAL_REVIEW",
  "sessions_seen": 2,
  "strong_full_grid_sessions": 1,
  "partial_coverage_sessions": 1,
  "baseline_count": 1,
  "diagnostic_count": 5,
  "variants_seen": ["base", "vol-off", "imb-off", "both-off"],
  "technical_summary": "Filtered technical evidence repeated across multiple sessions, including at least one strong-full-grid session.",
  "warnings": [],
  "requested_reviews": [
    "R10_CONTEXT_RISK",
    "R11_FINANCIAL_STATEMENT",
    "CSE_DISCLOSURE",
    "HUMAN_NOTES"
  ],
  "artifact_refs": {
    "dossier_markdown_path": ".runtime-pipeline/candidate-dossiers/PKME.N0000.md",
    "runtime_root": ".runtime-pipeline/multi-session-validation",
    "session_stems": [
      "atrad-session-20260602-040121",
      "atrad-session-20260602-042010"
    ]
  }
}
```

The purpose of this request is to carry technical evidence summary and artifact references forward. It is not intended to replace R10 source documents, R10 reports, or R11 dossiers.

## Candidate-to-R10 Handoff

The candidate-to-R10 handoff should provide source-bound candidate context, not trading intent.

R10 remains context/risk only. It should continue to operate inside its existing confirmed source boundary and validated output shapes. The bridge should reference or feed into existing R10 artifacts such as:

- `CseNewsAnalysis`
- `R10AnalysisReport`
- `R10PolicyDecision`

Allowed R10 policy labels remain:

- `SUPPORT`
- `BLOCK`
- `MANUAL_REVIEW`
- `NO_EFFECT`

R10 must not output buy/sell recommendations.

Draft R10 response reference shape:

```json
{
  "review_type": "R10_CONTEXT_RISK",
  "ticker": "PKME.N0000",
  "report_ref": {
    "report_id": "r10_ticker_context_20260603T000000Z_PKME.N0000",
    "schema_version": "r10_analysis_report_v1"
  },
  "analysis_ref": {
    "schema_version": "r10_news_analyst_v1",
    "analysis_scope": "TICKER",
    "signal_policy": "MANUAL_REVIEW"
  },
  "policy_ref": {
    "schema_version": "r10_policy_decision_v1",
    "r10_policy": "MANUAL_REVIEW"
  }
}
```

The bridge should prefer references to validated R10 artifacts over duplicating R10 fields into a parallel technical-review format.

## Candidate-to-R11 Handoff

R11 must not treat technical signal evidence as financial evidence.

The technical dossier can justify why a company should be reviewed, but R11 should still rely on:

- CSE financial statements
- CSE disclosures
- extracted tables
- Python-verified calculations
- source traces

R11 response should align with `R11AnalystDossier`.

Allowed future R11 labels for bridge-level status tracking:

- `FUNDAMENTALS_REVIEW_PENDING`
- `FUNDAMENTALS_REVIEWED`
- `MANUAL_REVIEW_REQUIRED`
- `INSUFFICIENT_FINANCIAL_DATA`

Draft R11 response reference shape:

```json
{
  "review_type": "R11_FINANCIAL_STATEMENT",
  "ticker": "PKME.N0000",
  "review_status": "FUNDAMENTALS_REVIEW_PENDING",
  "dossier_ref": {
    "dossier_id": "r11_dossier_PKME.N0000_20260603T000000Z",
    "schema_version": "r11_analyst_dossier_v1"
  },
  "notes": "Future bridge should reference validated R11 dossier artifacts rather than infer fundamentals from technical evidence."
}
```

The bridge may request R11 review, but it must not substitute for the underlying source-bound financial workflow.

## CSE Disclosure Review Attachment

`CSE_DISCLOSURE` may be requested through the bridge.

However, the actual disclosure evidence must come from R10-controlled CSE documents and metadata. The candidate dossier should not be treated as the disclosure source itself.

The bridge should treat disclosure review as an attached source-validation and context step, not as a property of the technical dossier.

## Manual Human Notes

Future manual notes should be represented as a separate human-authored object, not as an R10 or R11 internal field.

Draft future shape:

```json
{
  "review_status": "MANUAL_REVIEW",
  "reviewer": "pending",
  "reviewed_at": "pending",
  "notes": "pending",
  "follow_up_required": true
}
```

These notes should remain explicitly human-authored and separate from automated R10/R11 artifacts.

## Combined Manual Review Packet

The long-term manual review packet should combine:

- technical dossier
- R10 response
- R11 response
- CSE disclosure review
- manual human notes

This combined packet remains a research packet, not a trading instruction.

Allowed final labels for the combined packet:

- `SUPPORT`
- `BLOCK`
- `MANUAL_REVIEW`
- `NO_EFFECT`
- `INSUFFICIENT_EVIDENCE`

The combined packet must not introduce buy/sell/hold labels.

## Data Flow

Planned high-level flow:

```text
candidate_evidence_dossier.py Markdown/JSON later
-> CandidateContextRequest
-> R10 context/risk review
-> R11 financial statement review
-> CSE disclosure review
-> manual human notes
-> combined research packet
```

This flow is intentionally staged. The current repository only has the technical dossier and placeholders. The bridge defined here is the design boundary for later integration.

## Safety and Audit Requirements

- Every output must cite source documents or runtime artifacts.
- LLM outputs must be schema validated.
- Calculations must be Python verified.
- No hidden promotion to execution.
- No direct trading actions.
- Human review required.
- Runtime artifacts should not be committed.

Additional boundary rules:

- R10 stays inside its current source boundary and validated policy labels.
- R11 stays inside source-bound financial analysis and audited calculations.
- The technical dossier does not become a substitute for official disclosures or financial statements.

## Deferred Fields / Future Schema Work

The following fields should be deferred to a later schema and adapter phase:

- stable `request_id`
- `generated_at`
- formal `schema_version`
- persisted filter configuration
- dossier artifact id
- source document ids
- announcement ids
- disclosure ids
- requested disclosure period
- reviewer identity / timestamps / approval trail
- direct R10/R11 linkage ids

These fields are likely useful, but they should be added only when the bridge moves from documentation into actual schema design.

## Implementation Plan

- Stage 1: docs-only bridge design
- Stage 2: optional JSON export from candidate dossier
- Stage 3: `CandidateContextRequest` schema
- Stage 4: R10 request adapter
- Stage 5: R11 placeholder adapter
- Stage 6: combined manual review report

The intended order is conservative by design. The bridge should first become explicit and auditable before any adapter or integration code is introduced.
