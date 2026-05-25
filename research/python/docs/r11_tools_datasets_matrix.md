# Sentinel-CSE R11 Tools and Datasets Evaluation Matrix

## 1. Purpose

This document evaluates existing resources that may help R11, including financial reasoning datasets, benchmark repos, OCR/table extraction tools, formula libraries, architecture references, and future structured reporting formats.

This document does not expand the Sentinel-CSE live source boundary. R11 live evidence must come from R10-verified CBSL/CSE documents unless source curation later approves more sources.

These resources are evaluation aids, design references, parser candidates, benchmark inputs, or formula references. They are not live Sentinel-CSE sources.

See `research/python/docs/r11_teaching_from_finance_resources.md` for the R11.0C teaching strategy that explains how these resources inform R11 without expanding the production evidence boundary.

## 2. Evaluation Categories

- Financial reasoning datasets: benchmark datasets for numerical reasoning, table-and-text reasoning, and long-document financial QA.
- Finance LLM / benchmark repos: references for financial instruction formats, benchmark methodology, and evaluation design.
- Table extraction and OCR tools: candidate parsers for local CSE PDFs and scanned/table-heavy disclosures.
- Formula and ratio references: references for formula taxonomy and financial-ratio definitions.
- Architecture references: examples of financial data platform design, adapters, and integration patterns.
- Future structured reporting formats: structured disclosure formats that could reduce PDF parsing requirements later.

## 3. Decision Labels

- `USE_NOW`: acceptable for current use within the existing boundary, usually as a baseline or reference already present in the stack.
- `EVALUATE_NEXT`: high-priority candidate for controlled local evaluation before any dependency or workflow commitment.
- `REFERENCE_ONLY`: useful for design, formulas, taxonomy, prompts, or evaluation methodology, but not a runtime dependency or live source.
- `WATCHLIST`: monitor for future value, adoption, source availability, or ecosystem maturity before investing.
- `AVOID_FOR_NOW`: not appropriate for current R11 because of source-boundary, dependency, privacy, licensing, cost, or quality concerns.

## 4. Matrix Columns

| Category | Resource | Official Link | What It Is | Possible R11 Role | Direct Dependency? | Network/API Required? | Local/Offline Feasible? | License / Terms Check Needed? | CSE Fit | Risks | Initial Decision | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Financial reasoning datasets | FinQA | https://finqasite.github.io/ | Financial numerical reasoning dataset over reports. | Benchmark/design examples and reasoning-program inspiration. | No | No for local copy; yes to obtain externally. | Yes after dataset acquisition. | Yes | Medium | Not a live Sentinel-CSE source; dataset domain may not match CSE/SLFRS. | `EVALUATE_NEXT` | Review task format and compare with R11 calculation-audit needs. |
| Financial reasoning datasets | TAT-QA | https://nextplusplus.github.io/TAT-QA/ | Table-and-text financial QA dataset. | Benchmark for reasoning over financial tables plus commentary. | No | No for local copy; yes to obtain externally. | Yes after dataset acquisition. | Yes | High | Not a live Sentinel-CSE source; format may need loader mapping. | `EVALUATE_NEXT` | Prioritize for first benchmark-loader design. |
| Financial reasoning datasets | DocFinQA | https://arxiv.org/abs/2401.06915 | Long-document financial QA benchmark. | Later benchmark for annual reports and large PDFs. | No | No for paper review; dataset acquisition may require network. | Likely yes after acquisition. | Yes | Medium | Longer-context assumptions may differ from CSE disclosures. | `WATCHLIST` | Revisit after R11 schemas and table extraction exist. |
| Finance LLM / benchmark repos | FinGPT | https://github.com/ai4finance-foundation/fingpt | Finance LLM ecosystem and instruction dataset reference. | Study financial NLP tasks and finance instruction formats. | No | No for conceptual review; yes if cloning/downloading. | Yes for local reference after acquisition. | Yes | Low to Medium | Too broad; may encourage training before foundations are ready. | `REFERENCE_ONLY` | Review only for task taxonomy and evaluation ideas. |
| Finance LLM / benchmark repos | PIXIU / FinMA | https://arxiv.org/abs/2306.05443 | Financial LLM benchmark/instruction dataset reference. | Evaluation methodology reference. | No | No for paper review; dataset/repo access may require network. | Yes for local reference after acquisition. | Yes | Low to Medium | Not CSE-specific; not a live source. | `REFERENCE_ONLY` | Extract benchmark-design lessons later. |
| Table extraction and OCR tools | pypdf | https://pypi.org/project/pypdf/ | Baseline PDF text extraction library. | Existing R10 baseline for text extraction only. | Already present in R10 context | No | Yes | Yes | Medium | Not sufficient alone for table-heavy financial statements or scanned PDFs. | `USE_NOW` | Keep as baseline in extraction bakeoff. |
| Table extraction and OCR tools | Camelot | https://camelot-py.readthedocs.io/en/latest/ | Local table extraction from text-based PDFs into DataFrames/CSV/JSON/HTML/Markdown. | Low-cost candidate for text-based CSE financial tables. | Not yet | No | Yes if installed locally | Yes | High if PDFs are text-based | Setup dependencies may be annoying; unsuitable for scanned PDFs. | `EVALUATE_NEXT` | Test on local CSE disclosure fixtures during bakeoff. |
| Table extraction and OCR tools | Docling | https://www.docling.ai/ | Open-source/local document conversion and structure extraction candidate. | Candidate for table extraction, reading order, and document structure. | Not yet | No for local use if installed | Yes | Yes | Potentially High | Dependency complexity; actual CSE PDF performance unknown. | `EVALUATE_NEXT` | Compare against Camelot on same fixtures. |
| Table extraction and OCR tools | unstructured.io | https://docs.unstructured.io/ | Document partitioning and table extraction framework. | Candidate for extracting structured elements from PDFs. | Not yet | Maybe; depends on local vs API configuration. | Maybe; local hi-res may need extra models. | Yes | Medium | Dependency weight, local hi-res setup, OCR/model requirements, cost if API-based. | `EVALUATE_NEXT` | Evaluate only after lighter local candidates. |
| Table extraction and OCR tools | Mistral OCR | https://docs.mistral.ai/capabilities/OCR/basic_ocr/ | API-based OCR/document understanding candidate. | Potentially strong table-preserving OCR output in Markdown/HTML. | Not yet | Yes | No | Yes | Medium to High for scanned PDFs | API cost, network dependency, data privacy, rate limits, vendor lock-in. | `EVALUATE_NEXT` | Evaluate only with approved sample policy and privacy review. |
| Future structured reporting formats | XBRL / iXBRL | https://www.xbrl.org/ and https://www.xbrl.org/ixbrl/ | Structured financial reporting standards. | Future adapter if CSE reporting becomes available in structured format. | Not yet | Depends on source distribution. | Yes if local filings are available. | Yes | Potentially Very High | CSE availability and timeline uncertain. | `WATCHLIST` | Monitor CSE disclosure format evolution. |
| Formula and ratio references | FinanceToolkit | https://pypi.org/project/financetoolkit/ | Financial analysis and ratio toolkit. | Formula taxonomy and ratio-definition reference. | No | Depends on usage; not needed for reference. | Yes for local package, but not recommended yet. | Yes | Medium | Direct use may obscure formulas and audit traceability. | `REFERENCE_ONLY` | Review formula taxonomy, do not adopt as calculation core. |
| Formula and ratio references | financial-ratios / ratio packages | https://pypi.org/project/financial-ratios/ | Potential formula taxonomy/reference package. | Formula reference after source/license/test review. | No | No if local package installed, but no install now. | Potentially | Yes | Unknown | Maintenance, formula correctness, license, and test coverage unknown. | `REFERENCE_ONLY` | Keep on watchlist for formula taxonomy only. |
| Architecture references | OpenBB | https://github.com/OpenBB-finance/OpenBB | Financial data platform and integration ecosystem. | Architecture reference for adapters and financial-data platform design. | No | No for conceptual review; yes for live integrations. | Yes for local code review after acquisition. | Yes | Low as source, Medium as architecture | Must not become a live Sentinel-CSE data source. | `REFERENCE_ONLY` | Study adapter boundaries only if needed. |

## 5. Financial Reasoning Datasets

### FinQA

Official link: https://finqasite.github.io/

FinQA is a financial numerical reasoning dataset over reports. It may help R11 with benchmark and design examples, especially for reasoning-program inspiration where a question is answered through explicit computation steps.

Initial decision: `EVALUATE_NEXT` as a benchmark/design resource, not as a live Sentinel-CSE source.

### TAT-QA

Official link: https://nextplusplus.github.io/TAT-QA/

TAT-QA is a table-and-text financial QA dataset. It is highly relevant because R11 must reason over financial tables plus narrative commentary.

Initial decision: `EVALUATE_NEXT`.

TAT-QA must not be used as a live Sentinel-CSE source.

### DocFinQA

Official link: https://arxiv.org/abs/2401.06915

DocFinQA is a long-document financial QA benchmark. It may be useful later for annual reports and large PDFs once R11 has schemas, extraction adapters, and an evaluation harness.

Initial decision: `WATCHLIST`.

DocFinQA must not be used as a live Sentinel-CSE source.

## 6. Finance LLM / Benchmark Repos

### FinGPT

Official link: https://github.com/ai4finance-foundation/fingpt

FinGPT is a finance LLM ecosystem and instruction dataset reference. R11 can study its financial NLP task categories and instruction formats, but should not adopt it as a live source or training input before R11 foundations are built.

Initial decision: `REFERENCE_ONLY` for now.

### PIXIU / FinMA

Official link: https://arxiv.org/abs/2306.05443

PIXIU / FinMA is a financial LLM benchmark and instruction dataset reference. It may help shape evaluation methodology and compare finance reasoning tasks.

Initial decision: `REFERENCE_ONLY` for now.

## 7. Table Extraction and OCR Candidates

### pypdf

Official link: https://pypi.org/project/pypdf/

`pypdf` is a baseline PDF text extraction tool already used in R10. It remains useful as a low-cost baseline, but it is not sufficient alone for table-heavy financial statements.

Initial decision: `USE_NOW` as baseline only.

### Camelot

Official link: https://camelot-py.readthedocs.io/en/latest/

Camelot extracts tables from text-based PDFs into DataFrames, CSV, JSON, HTML, and Markdown. It is a good low-cost baseline candidate for text-based CSE PDFs.

Initial decision: `EVALUATE_NEXT`.

Risks: Camelot only works well for text-based PDFs, setup dependencies may be annoying, and it is not suitable for scanned PDFs.

### Docling

Official link: https://www.docling.ai/

Docling is an open-source/local document conversion and structure extraction candidate. It may help with table extraction, reading order, and document structure.

Initial decision: `EVALUATE_NEXT`.

Risks: dependency complexity and actual performance on CSE PDFs are unknown.

### unstructured.io

Official link: https://docs.unstructured.io/

unstructured.io is a document partitioning and table extraction framework. It is a candidate for extracting structured elements from PDFs.

Initial decision: `EVALUATE_NEXT`.

Risks: dependency weight, local hi-res setup, OCR/model requirements, and cost if API-based.

### Mistral OCR

Official link: https://docs.mistral.ai/capabilities/OCR/basic_ocr/

Mistral OCR is an API-based OCR/document understanding candidate. It may be strong for preserving tables as Markdown or HTML.

Initial decision: `EVALUATE_NEXT`.

Risks: API cost, network dependency, data privacy, rate limits, and vendor lock-in.

### XBRL / iXBRL future adapter

Official links:

- https://www.xbrl.org/
- https://www.xbrl.org/ixbrl/

XBRL and iXBRL are future structured reporting formats. If CSE moves toward XBRL/iXBRL, R11 should prefer this over PDF extraction.

Initial decision: `WATCHLIST`.

Risks: CSE availability and timeline are uncertain.

## 8. Formula and Ratio References

### FinanceToolkit

Official link: https://pypi.org/project/financetoolkit/

FinanceToolkit can be a reference for formula taxonomy and financial ratios. R11 should not blindly use it as the calculation core.

Initial decision: `REFERENCE_ONLY`.

Reason: R11 needs transparent formulas, CSE/SLFRS mapping, and `ToolAuditEntry` traceability.

### financial-ratios / ratio packages

Official link: https://pypi.org/project/financial-ratios/

Financial ratio packages may provide formula taxonomy references. They need source, license, maintenance, and test review before any dependency consideration.

Initial decision: `REFERENCE_ONLY` or `WATCHLIST`.

## 9. Architecture References

### OpenBB

Official link: https://github.com/OpenBB-finance/OpenBB

OpenBB is an architecture reference for financial data platforms and integrations. It is not a Sentinel-CSE live data source.

Initial decision: `REFERENCE_ONLY`.

## 10. Recommended First Evaluation Order

Parser/tool order:

1. pypdf baseline
2. Camelot
3. Docling
4. unstructured.io
5. Mistral OCR
6. XBRL/iXBRL watchlist

Dataset order:

1. TAT-QA
2. FinQA
3. DocFinQA later

Reason: TAT-QA is closest to table + text reasoning. FinQA is closest to numerical reasoning programs. DocFinQA is for longer reports later.

## 11. How Datasets Enter the Project

Intended architecture:

```text
External dataset file
-> DatasetLoader
-> R11BenchmarkCase
-> evaluator
-> score/report
```

Not:

```text
External dataset
-> live Sentinel-CSE source
```

Possible future modules:

```text
research/python/sentinel_research/agents/r11/evals/
  benchmark_case.py
  loaders/finqa_loader.py
  loaders/tatqa_loader.py
  scoring.py
```

Dataset files should live under ignored runtime/data folders, not committed to git:

```text
research/python/.r11_runtime/datasets/
```

## 12. How Tools Enter the Project

Tools should enter R11 through a controlled evaluation path:

- First evaluate with local fixtures.
- Then add an adapter interface.
- Then add a tool-specific adapter only if useful.
- No heavy dependency should be added before a bakeoff.

Possible future interface:

```text
TableExtractor.extract(path) -> list[ExtractedFinancialTable]
```

## 13. Immediate Recommendation

Do not train yet.

Do not install all tools yet.

Do not add OCR APIs yet.

Do not expand live sources yet.

Recommended next phases:

- R11.1 Schema Foundation
- R11.2 Python Calculation Toolbox
- R11.3 Table Extraction Bakeoff

## 14. Open Checks Before Dependency Adoption

- license
- package maintenance
- Windows support
- dependency size
- offline support
- API cost
- data privacy
- performance on actual CSE PDFs
- output structure quality
- ease of testing

## 15. Close

R11.0B is an evaluation map, not a commitment to any external tool.
