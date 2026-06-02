# R11 Four-Case Real PDF Validation Closeout

## 1. Closeout Decision

R11.11 is complete as a documentation-only closeout for the first four-case real CSE PDF validation manifest.

This is the first real multi-case R11 benchmark. It establishes a clean deterministic validation checkpoint across two bank and two non-bank disclosures using local runtime artifacts, but it is not yet evidence of broad sector-wide generalization.

## 2. Why Four-Case Validation Matters

The four-case validation matters because it moves R11 beyond single-case or single-sector spot checks.

This milestone provides the first compact benchmark that spans:

- two bank PDFs
- two non-bank PDFs
- multiple statement layouts
- multiple deterministic metric paths
- manifest-level pass/fail reporting across more than one issuer family

It is the first point where R11 can be described as having a real repeated local validation benchmark rather than a set of isolated case studies.

## 3. Cases Included

The local four-case manifest used these real CSE PDF cases:

- `COMB.N0000 / Commercial Bank of Ceylon PLC`
- `SAMP.N0000 / Sampath Bank PLC`
- `AEL.N0000 / Access Engineering PLC`
- `DIMO.N0000 / Diesel & Motor Engineering PLC`

Coverage interpretation:

- `COMB` and `SAMP` provide bank-sector validation coverage
- `AEL` and `DIMO` provide non-bank validation coverage
- together they form the first mixed-sector deterministic R11 checkpoint

## 4. Validation Result

Local runtime manifest result:

- `cases_total: 4`
- `cases_passed: 4`
- `cases_failed: 0`
- `cases_manual_review: 0`

Per-case result:

- `COMB.N0000`: `PASS`, `passed_count=7`
- `SAMP.N0000`: `PASS`, `passed_count=12`
- `AEL.N0000`: `PASS`, `passed_count=10`
- `DIMO.N0000`: `PASS`, `passed_count=10`

This means the full local manifest completed without failed validations and without residual manual-review flags in the current four-case set.

## 5. What This Proves

This milestone proves:

- deterministic R11 validation now passes across four real CSE PDFs
- the current path works across both bank and non-bank cases
- statement classification, metric extraction, aggregation, scorecard generation, and validation can all complete cleanly in a mixed-sector manifest
- the AEL and DIMO non-bank fixes integrated cleanly into the broader validation set
- R11 now has a real local benchmark that can be rerun as a regression checkpoint

Most importantly, this is the first real multi-case benchmark that demonstrates repeatable deterministic behavior beyond the original bank-only validation path.

## 6. What It Does Not Prove Yet

This closeout does not yet prove:

- broad sector generalization across the full CSE universe
- robustness across many non-bank reporting styles
- correctness for scanned or OCR-heavy PDFs
- correctness for highly irregular tables, weak statement markers, or unusual group/company disclosure patterns
- completeness of expected metric coverage for a future larger benchmark set

The current four-case result is strong as a foundation, but still narrow in total issuer count and layout diversity.

## 7. Runtime Artifact Boundary

This closeout is based on local runtime analysis JSONs, validation artifacts, and a local manifest run. Those artifacts remain runtime-only and must not be committed.

The following remain outside source control:

- `.r10_runtime/`
- `.r11_runtime/`
- downloaded PDFs
- analysis JSON files
- validation manifests
- validation reports
- scorecards
- other local inspection outputs

This document records the benchmark result and interpretation only. It does not promote runtime artifacts into Git.

## 8. Recommended Next Phase Toward Larger Validation / Teaching

Recommended next phase:

1. Expand the real-PDF validation set with more CSE issuers across additional non-bank sectors.
2. Define expected outputs more explicitly per case so the benchmark becomes a stronger gold-label validation set.
3. Add more layout diversity before making any claims about broader deterministic generalization.
4. Keep the current manifest style so future regressions can be measured against the four-case baseline.
5. Delay teaching or training-oriented work until a materially larger real-case benchmark and expectation set is documented.

The immediate goal should be benchmark expansion first, not premature model-teaching work.

## 9. Relationship to Future Training / FinQA Work

This milestone is a foundation for later gold-label datasets and future teaching or training experiments, including possible FinQA-style supervision work.

What it contributes to that future:

- a small but real validated benchmark
- mixed-sector examples with deterministic expected outcomes
- evidence that upstream fixes can be measured against real regression cases

What it does not justify yet:

- immediate large-scale training conclusions
- broad benchmark claims
- teaching on under-documented or weakly validated cases

Future training or FinQA-aligned work should begin only after more real CSE cases are documented, expected outputs are stabilized, and the benchmark is expanded beyond this initial four-case set.
