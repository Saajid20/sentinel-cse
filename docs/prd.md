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

## Runtime Modes

Sentinel-CSE defaults to `SHADOW` mode. In this mode the pipeline processes market snapshots, generates signals, records signal lifecycle events, and stores outcomes, but it does not send Telegram alerts and it does not place orders.

`PAPER_ALERT` mode is available only when explicitly configured by the application. It keeps the same signal and paper-tracking behavior, but sends alerts through the injected alert sender. It still does not place orders.

Real ATrad market observation is not connected yet. ATrad remains mock-only, and no runtime mode enables broker login, browser selectors, order placement, or auto-trading.

## ATrad Manual Session Capture

ATrad browser session capture is local-only. The `pnpm atrad:login` script opens a visible browser and requires the user to log in manually and complete 2FA manually before storage state is saved.

The storage state file is written to `playwright/.auth/atrad-storage-state.json`, which is ignored by Git. This step does not scrape market data, does not add ATrad selectors, does not automate credential entry, and does not enable order placement or auto-trading.

ATrad may require more than Playwright storage state alone to preserve a live logged-in session. For that case, `pnpm atrad:login -- --base-url <url> --persistent-profile` and `pnpm atrad:observe-once -- --base-url <url> --persistent-profile` can reuse the local browser profile stored at `playwright/.profiles/atrad`, which is also ignored by Git. No credentials are stored in code, and this still does not enable order placement or auto-trading.

## ATrad Observe-Once Read-Only Prototype

The `pnpm atrad:observe-once` script is a local read-only prototype that reuses the saved Playwright storage state and extracts visible Market Watch table rows only. It converts those rows into raw market snapshots, passes them through the market data sanitizer, and prints accepted/rejected counts with issues.

This command sends no Telegram alerts, writes no Supabase records, does not run the trading pipeline, and places no orders.

ATrad session restore may still fail even when storage state and a persistent profile were saved. For that case, `pnpm atrad:login-and-observe -- --base-url <url>` keeps the manual login and the read-only observation inside the same live browser context. The user still logs in manually, Market Watch observation remains read-only, and no order placement or auto-trading is enabled.

The current ATrad observation path reads visible Market Watch rows from the `Full Watch - Equity` view when that table is present. The user may need to manually select `Full Watch - Equity` before pressing Enter in the same-session flow. This still does not place orders, send Telegram alerts, write Supabase records, or run the trading pipeline.

## ATrad Local Session Recorder

The `pnpm atrad:record-session` command is a local read-only ATrad session recorder. It keeps the browser session open after manual login and records usable `Full Watch - Equity` snapshots to a local JSON file under `data/live-sessions/`, which is ignored by Git.

By default the recorder stores only usable high-confidence snapshots. Low-confidence rows are quarantined for diagnostics, and future custom watchlists can reduce noisy rows further. This recorder does not connect Telegram, Supabase, or the strategy pipeline, and it does not place orders or enable auto-trading.

## ATrad Recorded Session Replay

The `pnpm atrad:replay-session -- --input <path>` command replays a locally recorded ATrad session JSON file for research and backtesting. It uses only local JSON files, does not connect to live ATrad, and runs through the safe local replay path with no Telegram, no Supabase, no order placement, and no auto-trading.

Replay diagnostics now explain why a recorded session did or did not produce signals. These diagnostics do not change strategy thresholds; they highlight blockers such as missing VWAP or insufficient time-series history so future feature engineering and longer recordings can close the gap safely. This remains local-only research with no live trading or alerts.

The local replay feature builder derives strategy-supporting fields such as spread, order-book imbalance, VWAP estimates, volume-ratio estimates, and session-high-based trigger estimates from recorded ATrad sessions. These estimates are for replay and research only, do not loosen strategy thresholds, and do not enable live trading, alerts, Supabase writes, or orders.

The local comparison report can compare multiple recorded ATrad sessions side by side to show whether longer or denser recordings improve replay readiness. This is still local-only research with no live trading, alerts, Supabase writes, or orders.

## Telegram Delivery Boundary

Real Telegram delivery is optional and disabled unless an application explicitly wires a real sender. Future runtime configuration may pass `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` into the sender constructor, but the Telegram package must not read environment variables directly. The mock sender remains the default for tests and local paper-trading workflows.

For local manual verification only, `pnpm telegram:test` sends one fixed Telegram test message using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from the local shell environment. This command is optional, is not used by unit tests, and is not wired into the signal pipeline.

## Supabase Persistence Boundary

Supabase persistence is optional and not wired into the runtime pipeline yet. The database package exposes mapper helpers and repository interfaces so a future application can pass an already-created Supabase client into the adapter layer. `packages/db` must not read `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY`; those credentials must live only in a local `.env` file or shell environment and must never be committed.

For local manual verification only, first apply `packages/db/migrations/001_initial_schema.sql` to the Supabase project. Then `pnpm supabase:test` can insert and read back one harmless `market_snapshots` row using `SUPABASE_URL` plus either `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_ANON_KEY` from the local shell environment. This script is optional, is not used by unit tests, and is not wired into the trading pipeline.
