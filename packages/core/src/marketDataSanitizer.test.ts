import { describe, expect, it } from 'vitest';
import { MarketDataSanitizer } from './marketDataSanitizer.js';
import { RawMarketSnapshot } from './types.js';

const validRawSnapshot = (overrides: Partial<RawMarketSnapshot> = {}): RawMarketSnapshot => ({
  ticker: ' samp.n0000 ',
  timestamp: 1_000,
  lastPrice: 55,
  bestBid: 54.5,
  bestAsk: 55,
  bidDepth: 2_000,
  askDepth: 1_000,
  volume: 300,
  totalTurnover: 16_500,
  source: 'mock-observer',
  metadata: { channel: 'unit-test' },
  ...overrides
});

describe('MarketDataSanitizer', () => {
  it('accepts a valid raw snapshot', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot());

    expect(result.accepted).toBe(true);
    expect(result.snapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      timestamp: 1_000,
      lastPrice: 55,
      bestBid: 54.5,
      bestAsk: 55,
      bidDepth: 2_000,
      askDepth: 1_000,
      volume: 300,
      totalTurnover: 16_500
    });
    expect(result.issues).toEqual([]);
    expect(result.warnings).toEqual([]);
  });

  it('converts numeric strings to numbers', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(
      validRawSnapshot({
        timestamp: '1000',
        lastPrice: '55',
        bestBid: '54.5',
        bestAsk: '55',
        bidDepth: '2,000',
        askDepth: '1000',
        volume: '300',
        totalTurnover: '16500'
      })
    );

    expect(result.accepted).toBe(true);
    expect(result.snapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      timestamp: 1_000,
      lastPrice: 55,
      bestBid: 54.5,
      bestAsk: 55,
      bidDepth: 2_000,
      askDepth: 1_000,
      volume: 300,
      totalTurnover: 16_500
    });
  });

  it('rejects missing ticker', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot({ ticker: '   ' }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('MISSING_TICKER');
  });

  it('rejects invalid last price', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot({ lastPrice: 'bad-price' }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('INVALID_LAST_PRICE');
  });

  it('rejects invalid bid or ask values', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot({ bestBid: undefined, bestAsk: 'oops' }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('INVALID_BID_ASK');
  });

  it('rejects best bid greater than best ask', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot({ bestBid: 56, bestAsk: 55 }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('BID_GREATER_THAN_ASK');
  });

  it('rejects invalid volume', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizer.sanitize(validRawSnapshot({ volume: -1 }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('INVALID_VOLUME');
  });

  it('rejects unrealistic spread', () => {
    const sanitizer = new MarketDataSanitizer({ maxSpreadPercent: 2 });

    const result = sanitizer.sanitize(validRawSnapshot({ bestBid: 50, bestAsk: 55 }));

    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.code)).toContain('UNREALISTIC_SPREAD');
  });

  it('rejects duplicate snapshots', () => {
    const sanitizer = new MarketDataSanitizer();

    expect(sanitizer.sanitize(validRawSnapshot()).accepted).toBe(true);
    const duplicate = sanitizer.sanitize(validRawSnapshot());

    expect(duplicate.accepted).toBe(false);
    expect(duplicate.issues.map((issue) => issue.code)).toContain('DUPLICATE_SNAPSHOT');
  });

  it('rejects stale timestamps', () => {
    const sanitizer = new MarketDataSanitizer();

    expect(sanitizer.sanitize(validRawSnapshot({ timestamp: 2_000 })).accepted).toBe(true);
    const stale = sanitizer.sanitize(validRawSnapshot({ timestamp: 1_000, volume: 320 }));

    expect(stale.accepted).toBe(false);
    expect(stale.issues.map((issue) => issue.code)).toContain('STALE_TIMESTAMP');
  });

  it('rejects outlier price moves', () => {
    const sanitizer = new MarketDataSanitizer({ maxPriceMovePercentPerTick: 10 });

    expect(sanitizer.sanitize(validRawSnapshot({ lastPrice: 100, bestBid: 99, bestAsk: 100 })).accepted).toBe(true);
    const outlier = sanitizer.sanitize(validRawSnapshot({ timestamp: 2_000, lastPrice: 120, bestBid: 119, bestAsk: 120 }));

    expect(outlier.accepted).toBe(false);
    expect(outlier.issues.map((issue) => issue.code)).toContain('OUTLIER_PRICE_MOVE');
  });

  it('tracks state per ticker independently', () => {
    const sanitizer = new MarketDataSanitizer({ maxPriceMovePercentPerTick: 10 });

    const firstTicker = sanitizer.sanitize(validRawSnapshot({ ticker: 'SAMP.N0000', timestamp: 2_000, lastPrice: 100, bestBid: 99, bestAsk: 100 }));
    const secondTicker = sanitizer.sanitize(validRawSnapshot({ ticker: 'OTHER.N0000', timestamp: 1_000, lastPrice: 500, bestBid: 499, bestAsk: 500 }));
    const secondTickerUpdate = sanitizer.sanitize(validRawSnapshot({ ticker: 'OTHER.N0000', timestamp: 2_000, lastPrice: 505, bestBid: 504.5, bestAsk: 505 }));

    expect(firstTicker.accepted).toBe(true);
    expect(secondTicker.accepted).toBe(true);
    expect(secondTickerUpdate.accepted).toBe(true);
    expect(sanitizer.getLastAcceptedSnapshot('SAMP.N0000')?.lastPrice).toBe(100);
    expect(sanitizer.getLastAcceptedSnapshot('OTHER.N0000')?.lastPrice).toBe(505);
  });
});
