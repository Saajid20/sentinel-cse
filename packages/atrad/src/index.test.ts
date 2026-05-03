import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { MockATradObserver, MockATradSessionManager } from './index.js';

const watchlist = [
  {
    ticker: 'SAMP.N0000',
    enabled: true,
    displayName: 'Sample One',
    source: 'mock'
  },
  {
    ticker: 'DISABLED.N0000',
    enabled: false,
    source: 'mock'
  }
];

describe('MockATradSessionManager', () => {
  it('starts and stops a mock observation session', async () => {
    const manager = new MockATradSessionManager(() => 1_000);

    const started = await manager.startObservationSession();
    expect(started).toMatchObject({
      isAuthenticated: false,
      sessionStartedAt: 1_000,
      lastHeartbeatAt: 1_000
    });

    const stopped = await manager.stopObservationSession();
    expect(stopped.isAuthenticated).toBe(false);
    expect(stopped.notes).toContain('Mock observation session stopped.');
  });

  it('refreshes heartbeat', async () => {
    let now = 1_000;
    const manager = new MockATradSessionManager(() => now);

    await manager.startObservationSession();
    now = 2_000;

    const state = await manager.refreshHeartbeat();
    expect(state.lastHeartbeatAt).toBe(2_000);
    expect(state.notes).toContain('Mock heartbeat refreshed.');
  });
});

describe('MockATradObserver', () => {
  it('sets and retrieves a watchlist', async () => {
    const observer = new MockATradObserver();

    await observer.setWatchlist(watchlist);

    await expect(observer.getWatchlist()).resolves.toEqual(watchlist);
  });

  it('observeOnce returns mock snapshots for enabled tickers', async () => {
    const observer = new MockATradObserver(watchlist, () => 10_000);

    const snapshots = await observer.observeOnce();

    expect(snapshots).toHaveLength(1);
    expect(snapshots[0]).toMatchObject({
      ticker: 'SAMP.N0000',
      timestamp: 10_000,
      lastPrice: 50,
      bestBid: 49.5,
      bestAsk: 50.5
    });
  });

  it('observeMany returns multiple batches', async () => {
    const observer = new MockATradObserver(watchlist, () => 10_000);

    const batches = await observer.observeMany(3);

    expect(batches).toHaveLength(3);
    expect(batches.map((batch) => batch[0]?.lastPrice)).toEqual([50, 51, 52]);
  });

  it('does not use real Playwright or browser login code', () => {
    const source = readFileSync('packages/atrad/src/index.ts', 'utf8');

    expect(source).not.toMatch(/playwright/i);
    expect(source).not.toMatch(/chromium|firefox|webkit/i);
    expect(source).not.toMatch(/locator|selector|page\./i);
    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password/i);
  });
});
