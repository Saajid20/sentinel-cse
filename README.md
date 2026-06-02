# Sentinel-CSE

Sentinel-CSE is an open-source research infrastructure project for the Colombo Stock Exchange (CSE). It focuses on public CSE/CBSL data research, read-only ATrad session recording and replay, market-session quality validation, disclosure analysis, offline policy simulation, and future financial-statement parsing workflows.

The project is early-stage and research-only. It is not a live trading system.

## What This Is

- Research infrastructure for CSE market data and disclosure analysis.
- Read-only/session-replay tooling for local ATrad market-watch research.
- Market-session validation and reporting for recorded local sessions.
- Offline context/risk analysis foundation through the R10 research layer.
- Experimental paper-signal research environment for diagnostics and validation.
- A foundation for a future R11 institutional financial analyst layer focused on financial-statement parsing and analyst dossiers.

## What This Is Not

- Not a live trading bot.
- Not a broker automation system.
- Not financial advice.
- Not a buy/sell recommendation engine.
- Not production investment software.
- Not guaranteed accurate, complete, profitable, or suitable for real capital decisions.

## Why This Matters as OSS

CSE-focused tooling is under-served compared with larger global markets. Sentinel-CSE aims to provide a transparent research base for Sri Lankan market data quality, disclosure processing, session replay, and safety-first paper workflows. The repository is intended to help contributors inspect assumptions, improve parsers, strengthen validation, and build responsible local-market research infrastructure without live order execution.

## Current Capabilities

Capabilities below are based on tracked repository files and tests:

- Local read-only ATrad session recording and observe-once prototypes.
- Recorded-session replay diagnostics.
- Session quality summaries and session comparison reports.
- Universe candidate reports and local tradeable-universe validation.
- Strategy blocker reports and strategy variant comparison reports.
- Multi-session validation and compact aggregate reports.
- Filtered signal ticker reports.
- Local read-only operator dashboard and browser dashboard.
- CSE public API research probe and CSE-vs-ATrad cross-check reports.
- CBSL/CSE ingestion foundations in the R10 research layer.
- R10 context/risk filter foundation with offline policy simulation.
- R11 financial-statement parsing, validation, metric, and dossier research foundations.

Diagnostic strategy variants are for offline research only. They are not production recommendations.

## Architecture Overview

Sentinel-CSE is organized as a TypeScript workspace plus a separate Python research workspace:

- `packages/core`: shared market data types, sanitization, candle building, indicators, memory, and monitoring primitives.
- `packages/atrad`: ATrad parsing and read-only market-watch extraction boundaries.
- `packages/strategies`: strategy research logic and tests.
- `packages/db`: persistence interfaces and mapper helpers; Supabase is optional and not wired into live execution.
- `packages/telegram`: alert-sender abstractions and mocks; real Telegram delivery is optional/manual only.
- `apps/worker` and `apps/ingestor`: TypeScript application surfaces for pipeline and ingestion experiments.
- `scripts/`: local operator, dashboard, ATrad session, replay, and validation commands.
- `web/dashboard`: static read-only dashboard UI.
- `research/python`: offline session analysis, CSE/CBSL ingestion research, R10 policy/context tooling, and R11 financial analyst research.

The high-level flow is:

1. Data ingestion and local session capture from public sources or read-only ATrad market-watch observation.
2. Offline replay, diagnostics, and quality validation from local JSON session files.
3. Research reports for session health, strategy blockers, variants, and filtered ticker outputs.
4. R10 context/risk analysis over controlled CSE/CBSL/disclosure sources.
5. Future R11 financial analyst workflows for statement parsing, calculations, validation, and dossier generation.
6. Safety gates that keep the project read-only, research-only, and outside order execution.

## Safety Model

- No live trading.
- No order execution.
- No automated broker order-entry selectors.
- No financial advice.
- No buy/sell recommendations.
- Human review is required for all outputs.
- Research, education, and paper-trading workflows only.
- Local credentials, Playwright auth state, recorded sessions, generated reports, and `.env` files are ignored by Git.
- AI/LLM or parser outputs may be wrong and must be independently validated.

## Current Status

Sentinel-CSE is an early-stage research system. It has useful local tooling, tests, and research documentation, but it should be treated as experimental infrastructure. It is not production-ready investment software and must not be used to place trades or make automated financial decisions.

## Developer Setup

Prerequisites from repository metadata:

- Node.js `>=20.0.0`
- pnpm `>=8.0.0`
- Python 3 with `pip`

Install TypeScript workspace dependencies:

```powershell
pnpm install
```

Install Python research dependencies:

```powershell
python -m pip install -r research/python/requirements.txt
```

## Useful Local Commands

These commands are defined in `package.json` or documented in `research/python/README.md`:

```powershell
pnpm sentinel status
pnpm sentinel dashboard
pnpm dashboard
pnpm universe:validate
pnpm atrad:record-session
pnpm atrad:replay-session -- --input <path>
pnpm atrad:compare-sessions -- --input <path>
pnpm research:session:summary -- --input research/python/sample_data/sample_session.json
pnpm research:sessions:compare -- --input research/python/sample_data/sample_session.json --input research/python/sample_data/sample_session.json
pnpm research:cse-api:probe -- --endpoint marketStatus --dry-run
```

ATrad commands are local and read-only. Some require manual browser login or a local session file. Do not commit local session files, profiles, storage state, credentials, or generated reports.

## Tests And Checks

Real commands available in this repository:

```powershell
pnpm test
pnpm typecheck
pnpm build
pnpm research:python:test
python -m pytest research/python/tests
```

`pnpm research:python:test` and `python -m pytest research/python/tests` run the same Python test suite through different entry points.

## Documentation

- [Product and phase notes](docs/prd.md)
- [Project overview, safety, roadmap, and contributor guardrails](docs/project-overview.md)
- [Python research workspace](research/python/README.md)
- [R10 closeout](research/python/docs/r10_closeout.md)
- [R10 source architecture and onboarding](research/python/docs/r10_source_architecture_and_onboarding.md)
- [R11 architecture](research/python/docs/r11_architecture.md)
- [R11 deterministic v0.1 closeout](research/python/docs/r11_deterministic_v0_1_closeout.md)
- [R11 tools and datasets matrix](research/python/docs/r11_tools_datasets_matrix.md)
- [R11 validation manifest](research/python/docs/r11_validation_manifest.md)
- [R11 validation checklist](research/python/docs/r11_validation_checklist.md)

## Roadmap

- Improve data-source resilience and cautious CSE public API fallback research.
- Expand open-market session validation over more recorded sessions.
- Improve dashboard/reporting for local research review.
- Harden R10 context/risk filtering, disclosure ingestion, and offline policy simulation.
- Advance R11 financial-statement parsing, table extraction, deterministic calculations, and validation manifests.
- Strengthen documentation and contributor onboarding.
- Maintain safety, compliance, and no-order-execution guardrails.

## Contributing

Issues and small pull requests are welcome, especially for documentation, parser hardening, validation reports, test coverage, and onboarding improvements.

Please keep contributions inside the research-only scope:

- Add tests for logic changes.
- Do not include secrets, credentials, tokens, private URLs, private account information, or local session artifacts.
- Do not add live trading, order execution, broker automation, or buy/sell recommendation features.
- Keep generated reports and runtime artifacts out of Git.
- Be explicit about assumptions, data-source limits, and validation gaps.

## Disclaimer

Sentinel-CSE is for educational and research use only. It does not provide financial advice, trading recommendations, or live order execution. Users are responsible for compliance with local laws, broker terms, data-provider terms, and exchange rules. All outputs require human review, and AI/LLM, parser, replay, or diagnostic outputs may be wrong.
