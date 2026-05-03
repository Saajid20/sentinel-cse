# Sentinel-CSE PRD

## Product Summary

Sentinel-CSE is a signal-only and paper-trading bot for the Colombo Stock Exchange. It observes ATrad market data, builds its own candles and indicators, validates trade setups through a staged pipeline, sends Telegram alerts, tracks signal validity, records outcomes, and learns from historical signal performance.

## Current Scope

The first version is signal-only. It must not place orders or automate live trading.

## Core Pipeline

Scan → Detect → Validate → Size → Alert → Monitor → Learn

## v0.1 Goals

- Create a TypeScript monorepo.
- Build mock market data ingestion.
- Build candle generation.
- Build VWAP, spread, volume ratio, and order-book imbalance calculations.
- Implement CSE Opening Momentum v1.
- Send mock Telegram-style alerts.
- Store signal outcomes in a database interface.
- Track signal expiry and performance.

## Out of Scope for v0.1

- Auto-trading
- Order placement
- Market orders
- Real capital deployment
- Direct ATrad DOM order execution

## First Strategy

CSE Opening Momentum v1.

A BUY WATCH signal is generated only if:

- Price is above VWAP
- Price breaks the first 5-minute high
- Volume ratio is greater than 2
- Spread is below 1.5%
- Bid depth is stronger than ask depth
- Price is not near the upper price band
- ASPI kill switch is inactive

## Signal Validity

Opening momentum signals are valid for 10 minutes.

A signal expires earlier if:

- Price leaves the entry zone
- Price falls below VWAP
- Spread widens above 2%
- ASPI volatility kill switch is triggered
- Target or stop is hit

## Memory

Every signal must be stored with:

- Signal ID
- Ticker
- Strategy
- Timestamp
- Features at signal time
- Entry zone
- Stop loss
- Targets
- Valid until
- Status
- Max favorable move
- Max adverse move
- Outcome after 5 minutes
- Outcome after 15 minutes
- Outcome after 1 hour
- End-of-day outcome

## Safety Rules

- No auto-trading in v0.1.
- No order placement code.
- No broker credentials in Git.
- No `.env` commits.
- No Playwright session file commits.
- All trade recommendations are alerts only.

## Telegram Delivery Boundary

Real Telegram delivery is optional and disabled unless an application explicitly wires a real sender. Future runtime configuration may pass `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` into the sender constructor, but the Telegram package must not read environment variables directly. The mock sender remains the default for tests and local paper-trading workflows.

For local manual verification only, `pnpm telegram:test` sends one fixed Telegram test message using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from the local shell environment. This command is optional, is not used by unit tests, and is not wired into the signal pipeline.

## Supabase Persistence Boundary

Supabase persistence is optional and not wired into the runtime pipeline yet. The database package exposes mapper helpers and repository interfaces so a future application can pass an already-created Supabase client into the adapter layer. `packages/db` must not read `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY`; those credentials must live only in a local `.env` file or shell environment and must never be committed.

For local manual verification only, first apply `packages/db/migrations/001_initial_schema.sql` to the Supabase project. Then `pnpm supabase:test` can insert and read back one harmless `market_snapshots` row using `SUPABASE_URL` plus either `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_ANON_KEY` from the local shell environment. This script is optional, is not used by unit tests, and is not wired into the trading pipeline.
