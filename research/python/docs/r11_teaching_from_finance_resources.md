# R11 Teaching From Finance Resources

## 1. Purpose

This document explains how R11 should learn from external finance datasets, benchmarks, and tools without weakening Sentinel-CSE's production source boundary.

External resources help R11 design, test, and improve audited financial reasoning behavior. They are not production sources.

## 2. R11 Operating Principle

"LLM reasons. Python calculates. Schemas enforce. R10 supplies truth."

External resources are used only for:

- evaluation design
- prompt/workflow design
- benchmark construction
- table extraction experiments
- formula registry design
- provider comparison
- future fine-tuning decision support

Production evidence remains R10-verified CBSL/CSE documents unless future source curation expands the boundary.

## 3. High-Level Teaching Loop

```text
External dataset / tool reference
-> convert into R11 internal schema
-> run R11 on controlled example
-> validate strict JSON output
-> execute numeric calculations with Python
-> compare against gold answer / expected behavior
-> classify failure
-> patch correct R11 layer
-> rerun regression suite
```

## 4. Resource Map

| Resource | Main Role for R11 | Production Source? | R11 Usage |
| --- | --- | --- | --- |
| FinQA | Financial calculation reasoning benchmark | No | Teach and test multi-step numeric reasoning and formula choice under controlled evaluation. |
| TAT-QA | Table plus text evidence benchmark | No | Teach table-and-text evidence selection, answer grounding, and period alignment. |
| DocFinQA | Long-document financial QA benchmark | No | Teach long-document retrieval and evidence ranking for larger reports. |
| ConvFinQA | Multi-turn financial reasoning benchmark | No | Teach follow-up reasoning and stateful analyst-style questioning. |
| FinGPT | Finance LLM ecosystem reference | No | Inform provider comparison, task framing, and future fine-tuning decision support. |
| PIXIU / FinMA | Financial benchmark design reference | No | Inform failure taxonomy, evaluation methodology, and finance task coverage. |
| FinBen | Financial benchmark design reference | No | Inform benchmark breadth and provider comparison structure. |
| FinanceToolkit | Formula and ratio reference | No | Inform formula registry design and naming discipline. |
| financial-ratios packages | Formula reference | No | Inform ratio catalog review and formula cross-checking. |
| OpenBB | Architecture reference | No | Inform adapter boundaries and data-platform design patterns. |
| Camelot | Text-based PDF table extraction candidate | No | Teach extraction reliability on structured text PDFs through bakeoffs. |
| Docling | Document structure extraction candidate | No | Teach reading-order and table-structure preservation through bakeoffs. |
| unstructured.io | Structured document extraction candidate | No | Teach extraction robustness across different PDF layouts. |
| Mistral OCR | OCR/document understanding candidate | No | Teach OCR fallback quality in manual or gated evaluations only. |
| CSE disclosures | Local-market truth set | Yes, via R10 boundary | Specialize R11 for Sri Lankan listed-company financial reporting after generic teaching/evaluation layers are stable. |

## 5. Dataset Roles

- FinQA = calculation reasoning school
- TAT-QA = table + text evidence school
- DocFinQA = long-document retrieval school
- ConvFinQA = multi-turn analyst reasoning school

These datasets should enter through evaluation loaders, not production source stores.

## 6. Finance LLM / Benchmark Roles

- FinGPT = data-centric finance LLM reference
- PIXIU / FinMA / FinBen = benchmark design references

These are not production analysts yet. They are used later for provider comparison, evaluation design, and possible fine-tuning decision support.

## 7. Formula / Ratio Reference Role

FinanceToolkit and financial-ratios packages help formula registry design by showing common ratio names, groupings, and formula families.

R11 should still implement its own audited formula registry and calculation tools. Formula choice, denominators, units, and audit records must remain explicit inside Sentinel-CSE rather than delegated to third-party packages.

## 8. Table Extraction Teaching Role

`pypdf`, Camelot, Docling, unstructured.io, Mistral OCR, and future XBRL/iXBRL paths are evaluated through bakeoffs.

They teach extraction reliability. They do not expand live sources.

## 9. CSE-FinQA Future Local Dataset

A future local benchmark can be built from R10-verified CSE disclosures once schemas, extraction, calculation, and normalization are stable.

Illustrative record shape:

```json
{
  "case_id": "cse_finqa_comb_q1_2026_001",
  "ticker": "COMB.N0000",
  "question": "What was year-over-year growth in profit after tax?",
  "source_document_id": "doc-123",
  "expected_line_items": ["profit_after_tax"],
  "expected_periods": ["Q1 2026", "Q1 2025"],
  "expected_formula": "yoy_growth",
  "gold_answer": 0.124,
  "evidence_pages": [4]
}
```

This is future work after schemas, extraction, calculation, and normalization are stable.

## 10. Failure Taxonomy

- `SCHEMA_FAIL`
- `JSON_INVALID`
- `WRONG_EVIDENCE`
- `WRONG_TABLE`
- `WRONG_PAGE`
- `WRONG_PERIOD`
- `WRONG_SIGN`
- `WRONG_UNIT`
- `WRONG_FORMULA`
- `WRONG_DENOMINATOR`
- `CALCULATION_ERROR`
- `ROUNDING_ERROR`
- `HALLUCINATED_VALUE`
- `UNSAFE_TRADING_LANGUAGE`
- `INSUFFICIENT_EVIDENCE`
- `RETRIEVAL_FAILURE`
- `EXTRACTION_FAILURE`
- `NORMALIZATION_FAILURE`
- `SOURCE_TRACE_MISSING`
- `TOOL_AUDIT_MISSING`

Failures should patch the correct R11 layer. Extraction failures should improve extraction. Formula failures should improve the audited calculation layer. Schema failures should improve JSON validation and repair logic, not the source boundary.

## 11. Teaching Phases

- Phase A: No-LLM dataset adapters
- Phase B: Deterministic calculation tests
- Phase C: Single-turn R11 evaluation
- Phase D: Long-document retrieval evaluation
- Phase E: CSE-FinQA creation
- Phase F: Provider comparison
- Phase G: Fine-tuning decision

## 12. Safety Rules

External datasets and tools must never cause R11 to:

- output buy/sell/hold/order decisions
- connect to broker/ATrad/execution
- use external datasets as production evidence
- treat generic US examples as CSE truth
- calculate final metrics mentally with the LLM
- bypass Python verification or source tracing

## 13. Final Summary

FinQA teaches calculation reasoning.
TAT-QA teaches table + text evidence.
DocFinQA teaches long-document retrieval.
ConvFinQA teaches follow-up reasoning.
FinGPT teaches data-centric adaptation.
PIXIU / FinBen teaches benchmark design.
FinanceToolkit teaches formula transparency.
OpenBB teaches adapter architecture.
Table extraction tools teach extraction reliability.
CSE disclosures teach local-market specialization.
Python remains the calculator.
Pydantic remains the guardrail.
R10 remains the source boundary.
