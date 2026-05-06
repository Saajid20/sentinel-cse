import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  assertATradReadOnlySafety,
  ATradReadOnlyPageAdapter,
  ATradObservedTicker,
  checkATradReadOnlySafety,
  MockATradObserver,
  MockATradSessionManager,
  PlaywrightATradObserver,
  PlaywrightATradObserverConfig,
  PlaywrightATradSessionManager
} from './index.js';

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

  it('does not use browser login, environment config, or page selectors', () => {
    const source = readFileSync('packages/atrad/src/index.ts', 'utf8');

    expect(source).not.toMatch(/chromium|firefox|webkit/i);
    expect(source).not.toMatch(/locator|selector|page\./i);
    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password/i);
  });
});

describe('PlaywrightATradSessionManager', () => {
  it('uses constructor config and does not read environment variables', async () => {
    const manager = new PlaywrightATradSessionManager(
      sessionConfig({ storageStatePath: 'playwright/.auth/manual-state.json' }),
      () => 5_000
    );

    const state = await manager.getSessionState();

    expect(state.storageStatePath).toBe('playwright/.auth/manual-state.json');
    expect(readFileSync('packages/atrad/src/index.ts', 'utf8')).not.toMatch(/process\.env/);
  });

  it('starts and stops a read-only observation session', async () => {
    const manager = new PlaywrightATradSessionManager(sessionConfig(), () => 10_000);

    const started = await manager.startObservationSession();
    const stopped = await manager.stopObservationSession();

    expect(started).toMatchObject({
      isAuthenticated: false,
      sessionStartedAt: 10_000,
      lastHeartbeatAt: 10_000,
      storageStatePath: 'playwright/.auth/storageState.json'
    });
    expect(started.notes.join(' ')).toContain('read-only');
    expect(stopped.isAuthenticated).toBe(false);
    expect(stopped.notes).toContain('Playwright ATrad read-only observation session stopped.');
  });

  it('refreshes heartbeat without launching a browser', async () => {
    let now = 20_000;
    const manager = new PlaywrightATradSessionManager(sessionConfig(), () => now);

    await manager.startObservationSession();
    now = 21_000;
    const state = await manager.refreshHeartbeat();

    expect(state.lastHeartbeatAt).toBe(21_000);
    expect(state.notes).toContain('Playwright ATrad read-only heartbeat refreshed.');
  });

  it('requires readonlyMode true', () => {
    expect(() => new PlaywrightATradSessionManager({ ...sessionConfig(), readonlyMode: false } as any)).toThrow(
      /readonlyMode: true/
    );
  });
});

describe('PlaywrightATradObserver', () => {
  it('sets and retrieves a watchlist', async () => {
    const observer = new PlaywrightATradObserver(new MockATradSessionManager(), observerConfig());

    await observer.setWatchlist(watchlist);

    await expect(observer.getWatchlist()).resolves.toEqual(watchlist);
  });

  it('observeOnce returns empty scaffold results when no page adapter is provided', async () => {
    const observer = new PlaywrightATradObserver(new MockATradSessionManager(), observerConfig());

    await expect(observer.observeOnce()).resolves.toEqual([]);
  });

  it('uses an injected read-only page adapter without launching a real browser', async () => {
    const calls: ATradObservedTicker[][] = [];
    const adapter: ATradReadOnlyPageAdapter = {
      async observeReadOnlySnapshots(tickers) {
        calls.push(tickers);
        return [
          {
            ticker: tickers[0]?.ticker ?? 'UNKNOWN.N0000',
            timestamp: 1_000,
            lastPrice: 50,
            bestBid: 49.5,
            bestAsk: 50.5,
            bidDepth: 1_000,
            askDepth: 900,
            volume: 100,
            totalTurnover: 5_000
          }
        ];
      }
    };
    const observer = new PlaywrightATradObserver(new MockATradSessionManager(), observerConfig(), adapter);

    const snapshots = await observer.observeOnce();

    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual([watchlist[0]]);
    expect(snapshots).toMatchObject([{ ticker: 'SAMP.N0000', lastPrice: 50 }]);
  });

  it('observeMany calls observeOnce for the requested safe count', async () => {
    let calls = 0;
    const adapter: ATradReadOnlyPageAdapter = {
      async observeReadOnlySnapshots() {
        calls += 1;
        return [];
      }
    };
    const observer = new PlaywrightATradObserver(new MockATradSessionManager(), observerConfig(), adapter);

    const batches = await observer.observeMany(3.8);

    expect(batches).toHaveLength(3);
    expect(calls).toBe(3);
  });

  it('requires readonlyMode true', () => {
    expect(() => new PlaywrightATradObserver(new MockATradSessionManager(), { ...observerConfig(), readonlyMode: false } as any)).toThrow(
      /readonlyMode: true/
    );
  });

  it('does not expose order placement methods', () => {
    const sessionMethods = Object.getOwnPropertyNames(PlaywrightATradSessionManager.prototype);
    const observerMethods = Object.getOwnPropertyNames(PlaywrightATradObserver.prototype);
    const forbiddenMethodTerms = /buy|sell|order|submit|confirm|quantity/i;

    expect([...sessionMethods, ...observerMethods]).not.toEqual(
      expect.arrayContaining([expect.stringMatching(forbiddenMethodTerms)])
    );
  });
});

describe('ATrad read-only safety guard', () => {
  it('allows read-only observation descriptions', () => {
    expect(checkATradReadOnlySafety('read ticker table values only')).toEqual({
      safe: true,
      violations: []
    });
    expect(() => assertATradReadOnlySafety('read market depth display only')).not.toThrow();
  });

  it('rejects action descriptions with order-related terms', () => {
    const result = checkATradReadOnlySafety('click buy order submit button with quantity and price input');

    expect(result.safe).toBe(false);
    expect(result.violations).toEqual(
      expect.arrayContaining(['buy', 'order', 'submit', 'quantity', 'price input'])
    );
    expect(() => assertATradReadOnlySafety('confirm market order')).toThrow(/Unsafe ATrad read-only action/);
  });
});

function sessionConfig(overrides: Partial<PlaywrightATradObserverConfig> = {}): PlaywrightATradObserverConfig {
  return {
    baseUrl: 'https://example.invalid/atrad',
    storageStatePath: 'playwright/.auth/storageState.json',
    headless: true,
    watchlist,
    observationTimeoutMs: 5_000,
    readonlyMode: true,
    ...overrides
  };
}

function observerConfig(overrides: Partial<PlaywrightATradObserverConfig> = {}): PlaywrightATradObserverConfig {
  return sessionConfig(overrides);
}
