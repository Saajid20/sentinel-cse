# R10 Source Architecture And Onboarding

## 1. Purpose

This note documents how R10 is structured today as the source boundary for Sentinel-CSE, what source families are currently in use, and the required process for adding new sources safely.

R10 owns:

- source discovery
- source download
- source verification
- local document storage

R11 consumes local R10-sourced files and should not download source PDFs directly.

## 2. R10 Role As The Source Boundary

R10 is responsible for turning an external source into a controlled local artifact, typically:

- a local PDF
- a local HTML/text/JSON document
- a `SourceDocument` stored in the local R10 document store

That boundary exists to keep:

- source access logic
- file acquisition
- runtime provenance
- local storage metadata

out of the R11 analysis layer.

## 3. Confirmed Source Families

### CONFIRMED: CBSL

Status: `CONFIRMED`

Current shape:

- explicit/manual URL-based sourcing
- local ingestion through existing document-source adapters

### CONFIRMED: CSE

Status: `CONFIRMED`

Current shape:

- general announcements lookup
- announcement detail document fetch by `announcement_id`
- explicit CSE CDN PDF URL fetch and local ingestion

### CONFIRMED: Local / Manual Ingestion

Status: `CONFIRMED`

Current shape:

- local files
- local PDFs
- manual explicit URLs when the source path is already known

## 4. Current CSE Paths

### 4.1 General announcements

Status: `CONFIRMED`

Current helper:

- `research/python/scripts/r10_lookup_cse_announcements.py`

Current backend path:

- `getAnnouncementByCompany`

Use case:

- list general announcements and corporate disclosures by ticker/date range

### 4.2 Announcement PDF fetch by `announcement_id`

Status: `CONFIRMED`

Current helper:

- `research/python/scripts/r10_fetch_cse_announcement_pdf.py`

Current backend path:

- `getGeneralAnnouncementById`

Use case:

- inspect one announcement detail
- choose one attached document
- download and ingest that PDF locally

### 4.3 Explicit CSE PDF URL fetch

Status: `CONFIRMED`

Current helper:

- `research/python/scripts/r10_fetch_cse_pdf_url.py`

Use case:

- when the exact CSE CDN PDF URL is already known
- download locally
- ingest into the local document store

This is the correct existing fallback when discovery is incomplete but the target PDF URL is known.

### 4.4 Financial reports discovery

Status: `PLANNED`

Current finding:

- the existing general announcement path is not the same as the CSE financial reports path
- for `JKH` and `DIAL`, the general announcement lookup returned AGM notices, dividends, director changes, and corporate disclosures rather than actual financial statement PDFs
- `cse_public_api_probe.py` references `getFinancialAnnouncement`
- no production R10 helper currently wraps that financial-reports feed

Conclusion:

Financial reports should not be sourced through the general announcements path.

## 5. R10 To R11 Handoff Contract

The expected contract is:

`external source -> R10 local artifact -> R11 deterministic analysis`

Minimum handoff from R10 to R11:

- local file path
- ticker
- company
- source URL if known
- published/report date if known
- source metadata sufficient to identify the document later

R11 should receive a local verified path, not a website URL to fetch itself.

## 6. Source Status Labels

Use the following labels when documenting or proposing source work:

- `CONFIRMED`
  - implemented and exercised through the intended local ingestion path
- `PROBED`
  - observed through research/probe tooling, but not yet wrapped as a production R10 helper
- `PLANNED`
  - known gap with a defined intended helper shape
- `DEFERRED`
  - intentionally postponed due to lower priority, complexity, or dependency on later architecture
- `REJECTED`
  - intentionally not adopted because it conflicts with safety, reliability, maintenance, or architecture constraints

Current examples:

- CBSL source path: `CONFIRMED`
- CSE general announcements: `CONFIRMED`
- CSE financial reports feed via `getFinancialAnnouncement`: `PROBED`
- dedicated financial reports discovery helper: `PLANNED`

## 7. New Source Onboarding Protocol

Before implementing any new source adapter or helper:

1. Manually inspect the source first
   - website
   - document links
   - file-hosting behavior
   - whether files are actually present where expected

2. Identify where the required files actually reside
   - page HTML
   - API response
   - CDN path
   - secondary document endpoint

3. Identify source characteristics
   - file type
   - URL pattern
   - required metadata
   - date/ticker filters
   - paging shape
   - access constraints
   - anti-automation constraints if any

4. Decide the correct ingestion shape
   - discovery/list helper
   - explicit URL fetch
   - direct adapter/client method
   - parser
   - OCR path
   - manual fallback

5. Only then implement the adapter/helper
   - keep the first version narrow
   - prefer explicit metadata
   - prefer typed models for stable API responses
   - reuse existing local ingestion/store logic where possible

This protocol exists to avoid building helpers against the wrong source family or against superficial page behavior.

## 8. Current Finding: CSE Financial Reports

The important current architectural finding is:

The CSE financial reports path should not be treated as the same source family as general announcements.

General announcement lookup is appropriate for:

- corporate disclosures
- announcement detail PDFs

It is not sufficient for financial statement discovery.

The likely correct next source family is:

- CSE financial reports feed/page/API
- likely producing report metadata and `cmt/upload_report_file/...pdf` URLs

## 9. Recommended Next Helper

Recommended next helper:

- `research/python/scripts/r10_lookup_cse_financial_reports.py`

Intended behavior:

- query the financial reports feed, not general announcements
- filter by ticker/date range/report type
- print candidate report metadata
- print the PDF URL
- optionally hand off to `r10_fetch_cse_pdf_url.py` for local download and ingestion

This keeps discovery and explicit URL ingestion cleanly separated while reusing existing R10 PDF URL fetch logic.

## 10. Safety Boundaries

R10 source work must stay inside these boundaries unless explicitly changed later:

- no DeepSeek unless explicitly requested
- no R11 source downloading
- no trading outputs
- no buy/sell/hold/order language
- no broker/live-engine changes
- no ATrad/session/execution/order code changes for source work
- no runtime artifacts committed
- no aggressive scraping

Networked source access remains a manual research/runtime activity, not a committed test behavior.

## 11. Final Summary

R10 is the source boundary for Sentinel-CSE. Today it has confirmed support for CBSL, CSE general announcements, and explicit CSE PDF URL ingestion. The current gap is financial-report discovery from the dedicated CSE financial reports path, which appears to be separate from the general announcements backend. The next safe step is a narrow financial-reports discovery helper that identifies candidate report PDFs and then reuses the existing explicit CSE PDF URL fetch path for local storage and handoff to R11.
