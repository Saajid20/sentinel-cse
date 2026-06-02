# Sentinel-CSE Project Overview

This document summarizes the public project scope, safety boundary, roadmap, and contributor expectations for Sentinel-CSE.

Sentinel-CSE is open-source research infrastructure for the Colombo Stock Exchange. It should be understood as a research system, not as a live trading bot or production investment product.

## Public Positioning

Sentinel-CSE supports research into CSE market data quality, read-only ATrad session replay, disclosure and announcement analysis, R10 context/risk filtering, offline policy simulation, and future R11 financial-statement parsing workflows.

The project is useful for contributors who want to improve local-market data tooling, validation, parser quality, reporting, and safe research workflows for an under-served market ecosystem.

## Safety Boundary

- No live trading.
- No order execution.
- No broker automation.
- No financial advice.
- No buy/sell recommendations.
- No production investment claims.
- Human review is required.
- Research, education, and paper-trading workflows only.
- Diagnostic strategy variants are not production recommendations.
- Outputs from parsers, replay diagnostics, reports, or AI/LLM-backed tooling may be wrong and must be validated.

Users are responsible for complying with local laws, broker terms, exchange rules, public data-source terms, and any applicable disclosure/data-use requirements.

## Maintainer Notes

- The root README explains the project scope, safety model, architecture, setup, tests, roadmap, and contribution boundaries.
- Runtime artifacts are ignored by Git, including `.env` files, Playwright auth/profile data, local ATrad sessions, Python caches, and generated research reports.
- The repository includes TypeScript and Python tests covering core primitives, ATrad boundaries, dashboards, replay/reporting tools, R10 ingestion/policy tooling, and R11 parsing/validation foundations.
- Public documentation should avoid adoption metrics, production-readiness claims, financial-advice language, and trading-performance claims unless separately proven.
- Future contributor onboarding should keep a strict distinction between local research tooling and live broker/data-provider systems.

## Roadmap

Short realistic phases:

- Data-source resilience and cautious CSE public API fallback research.
- Broader open-market session validation with more locally recorded sessions.
- Dashboard and reporting improvements for operator review and contributor debugging.
- R10 hardening for source boundaries, disclosure context, risk filters, and offline policy simulation.
- R11 financial-statement parsing, deterministic calculations, validation manifests, and analyst dossier research.
- Documentation, examples, and contributor onboarding.
- Safety, compliance, and no-order-execution guardrails.

## Contributor Guardrails

Contributions are welcome when they strengthen research infrastructure without crossing into live trading or advice:

- Documentation improvements, small PRs, and focused issues are welcome.
- Tests are required for logic changes.
- Do not submit secrets, credentials, tokens, private URLs, private account data, local ATrad sessions, Playwright auth/profile files, or generated runtime reports.
- Do not add live trading, order placement, broker automation, or buy/sell recommendation features.
- Keep diagnostic strategy variants clearly labeled as offline research tools.
