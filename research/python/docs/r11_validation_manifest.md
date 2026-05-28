# R11 Validation Manifest

R11.8A3 adds a small local manifest format for defining multiple deterministic R11 validation cases without building the full multi-case runner yet.

## Purpose

The manifest is a compact validation plan for real-document checkpoints such as:

- COMB Q1 2026 known-good deterministic analysis
- the next banking disclosure
- the next non-bank interim statement
- later difficult or table-heavy cases

Each case points at an existing local deterministic analysis JSON artifact and stores the explicit expectations that `r11_validate_analysis_json.py` already knows how to enforce.

## Schema

The manifest lives under `research/python/sentinel_research/agents/r11/validation/manifest.py` and defines:

- `ExpectedStatementPage`
- `R11ValidationCase`
- `R11ValidationManifest`
- `load_validation_manifest(...)`
- `save_validation_manifest(...)`
- `validation_case_to_cli_args(...)`

The schema version is fixed to `r11_validation_manifest_v1`.

## Example

```json
{
  "schema_version": "r11_validation_manifest_v1",
  "cases": [
    {
      "case_id": "comb_q1_2026_known_good",
      "ticker": "COMB.N0000",
      "company_name": "Commercial Bank of Ceylon PLC",
      "description": "Known-good deterministic COMB validation case.",
      "analysis_json_path": "research/python/.r11_runtime/analysis/comb_q1_2026_deterministic_analysis.json",
      "expected_pages": [
        { "page_number": 5, "statement_type": "INCOME_STATEMENT" },
        { "page_number": 7, "statement_type": "BALANCE_SHEET" }
      ],
      "min_verified_metrics": 10,
      "min_aggregated_metrics": 10,
      "expect_manual_review": false,
      "require_scorecard": true,
      "require_no_conflicts": true,
      "notes": "Local runtime artifact only."
    }
  ],
  "notes": "Initial manual validation plan."
}
```

## Connection To The Manual Runner

`validation_case_to_cli_args(...)` converts one manifest case into CLI arguments that are directly compatible with:

`research/python/scripts/r11_validate_analysis_json.py`

That keeps the manifest format separate from execution while locking the case definition to the existing manual runner contract.

## Runtime Path Boundary

`analysis_json_path` values are expected to reference local runtime JSON artifacts, typically under `.r11_runtime`, but those runtime files are not committed.

The manifest stores the plan, not the artifact contents. This keeps real runtime outputs and real PDFs out of Git while still letting the validation plan be reviewed and extended.

## Next Step

The next phase can add a small multi-case runner that:

- loads one manifest
- iterates cases locally
- invokes the existing manual validation runner per case
- summarizes PASS / FAIL / MANUAL_REVIEW across the plan

This phase stops at schema, helpers, serialization, and documentation only.
