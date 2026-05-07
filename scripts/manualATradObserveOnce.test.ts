import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import { MarketDataSanitizer } from '../packages/core/src/index.js';
import { ATRAD_STORAGE_STATE_PATH } from './manualATradLogin.js';
import {
  createManualATradObserveOnceConfig,
  DEFAULT_ATRAD_MARKET_WATCH_URL,
  extractVisibleMarketWatchRows,
  ManualATradObserveOnceRuntime,
  marketWatchRowToRawSnapshot,
  sanitizeMarketWatchRows,
  runManualATradObserveOnce
} from './manualATradObserveOnce.js';

const fakeMarketWatchRow = {
  Security: 'SAMP.N0000',
  'Bid Qty': '1,000',
  'Bid Price': '54.50',
  'Ask Price': '55.00',
  'Ask Qty': '800',
  Last: '55.00',
  'Last Qty': '100',
  Change: '1.00',
  '% Change': '1.85',
  High: '56.00',
  Low: '53.00',
  VWA: '54.20',
  Volume: '12,500',
  Turnover: '687,500',
  Trades: '42',
  Time: '10:35:00'
};

describe('manual ATrad observe-once helpers', () => {
  it('returns a helpful result when storage state is missing', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: false,
      calls
    });

    const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(), runtime);

    expect(result.ok).toBe(false);
    expect(result.message).toContain('Run pnpm atrad:login first');
    expect(calls).not.toContain('launch');
  });

  it('maps a Market Watch row to a RawMarketSnapshot', () => {
    const rawSnapshot = marketWatchRowToRawSnapshot(fakeMarketWatchRow, 1_000);

    expect(rawSnapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      lastPrice: '55.00',
      bestBid: '54.50',
      bestAsk: '55.00',
      bidDepth: '1,000',
      askDepth: '800',
      volume: '12,500',
      totalTurnover: '687,500',
      timestamp: 1_000,
      source: 'atrad-market-watch'
    });
    expect(rawSnapshot.metadata).toMatchObject({
      high: '56.00',
      low: '53.00',
      vwa: '54.20',
      trades: '42',
      rawRow: fakeMarketWatchRow
    });
  });

  it('sanitizes numeric strings with commas from Market Watch rows', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizeMarketWatchRows([fakeMarketWatchRow], 1_000, sanitizer);

    expect(result.accepted).toHaveLength(1);
    expect(result.rejected).toHaveLength(0);
    expect(result.accepted[0]?.snapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      bidDepth: 1_000,
      volume: 12_500,
      totalTurnover: 687_500
    });
  });

  it('rejects unsafe action descriptions through the read-only guard', () => {
    expect(() => assertATradReadOnlySafety('read Market Watch table data')).not.toThrow();
    expect(() => assertATradReadOnlySafety('click buy order submit control')).toThrow(
      /Unsafe ATrad read-only action/
    );
  });

  it('extracts rows through an injected fake page without a real browser', async () => {
    let evaluateInput: string | (() => unknown) | undefined;
    const rows = await extractVisibleMarketWatchRows({
      async goto() {
        throw new Error('goto should not be called by extractor');
      },
      async evaluate(pageFunction) {
        evaluateInput = pageFunction;
        return [fakeMarketWatchRow];
      }
    });

    expect(rows).toEqual([fakeMarketWatchRow]);
    expect(typeof evaluateInput).toBe('string');
    expect(String(evaluateInput)).not.toContain('__name');
  });

  it('runs observe-once with an injected fake browser runtime', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls
    });

    const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(), runtime);

    expect(result.ok).toBe(true);
    expect(result.rawRows).toEqual([fakeMarketWatchRow]);
    expect(result.accepted).toHaveLength(1);
    expect(calls).toEqual(
      expect.arrayContaining([
        'launch',
        `context:${ATRAD_STORAGE_STATE_PATH}`,
        'new-page',
        `goto:${new URL(DEFAULT_ATRAD_MARKET_WATCH_URL).toString()}`,
        'close'
      ])
    );
  });

  it('does not read credentials, environment variables, or include unsafe action strings', () => {
    const source = readFileSync('scripts/manualATradObserveOnce.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password|otp/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|quantity input|price input|market order|limit order/i);
    expect(source).not.toMatch(/click\(|fill\(|type\(/);
  });
});

function fakeRuntime({
  storageStateExists,
  calls
}: {
  storageStateExists: boolean;
  calls: string[];
}): ManualATradObserveOnceRuntime {
  return {
    async storageStateExists() {
      return storageStateExists;
    },
    async launchBrowser() {
      calls.push('launch');
      return {
        async newContext(options: { storageState: string }) {
          calls.push(`context:${options.storageState}`);
          return {
            async newPage() {
              calls.push('new-page');
              return {
                async goto(url: string) {
                  calls.push(`goto:${url}`);
                },
                async evaluate() {
                  return [fakeMarketWatchRow];
                }
              };
            }
          };
        },
        async close() {
          calls.push('close');
        }
      };
    },
    now: () => 1_000,
    log: (message) => calls.push(`log:${message}`)
  };
}
