import { describe, expect, it } from 'vitest';
import { BasicMonitorAgent } from './monitor.js';
import { MarketSnapshot, Signal } from './types.js';

const baseSignal: Signal = {
  id: 'sig-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  timestamp: 1_000,
  type: 'BUY_WATCH',
  entryZone: [99, 101],
  stopLoss: 95,
  targets: [105, 110],
  validUntil: 601_000,
  features: {
    vwap: 98
  },
  status: 'ACTIVE'
};

const baseSnapshot: MarketSnapshot = {
  ticker: 'SAMP.N0000',
  timestamp: 60_000,
  lastPrice: 100,
  bestBid: 99.5,
  bestAsk: 100,
  bidDepth: 1_000,
  askDepth: 900,
  volume: 10_000,
  totalTurnover: 1_000_000
};

describe('BasicMonitorAgent', () => {
  const monitor = new BasicMonitorAgent();

  it('keeps a signal ACTIVE inside the validity window', async () => {
    const signal = await monitor.monitor(baseSignal, baseSnapshot);

    expect(signal.status).toBe('ACTIVE');
    expect(signal.latestPrice).toBe(100);
    expect(signal.lastCheckedAt).toBe(60_000);
    expect(signal.statusReason).toBe('Signal remains valid');
  });

  it('marks a signal EXPIRED after validUntil', async () => {
    const signal = await monitor.monitor(baseSignal, {
      ...baseSnapshot,
      timestamp: 601_001
    });

    expect(signal.status).toBe('EXPIRED');
    expect(signal.statusReason).toBe('Signal validity window elapsed');
  });

  it('marks a signal INVALIDATED when price falls below VWAP', async () => {
    const signal = await monitor.monitor(baseSignal, {
      ...baseSnapshot,
      lastPrice: 97,
      bestBid: 96.8,
      bestAsk: 97
    });

    expect(signal.status).toBe('INVALIDATED');
    expect(signal.statusReason).toBe('Price fell below VWAP');
  });

  it('marks a signal INVALIDATED when spread exceeds 2%', async () => {
    const signal = await monitor.monitor(baseSignal, {
      ...baseSnapshot,
      bestBid: 97.5,
      bestAsk: 100
    });

    expect(signal.status).toBe('INVALIDATED');
    expect(signal.statusReason).toBe('Spread exceeded 2%');
  });

  it('marks a signal TARGET_HIT when target is reached', async () => {
    const signal = await monitor.monitor(baseSignal, {
      ...baseSnapshot,
      lastPrice: 105,
      bestBid: 104.5,
      bestAsk: 105
    });

    expect(signal.status).toBe('TARGET_HIT');
    expect(signal.statusReason).toBe('Target 105 reached');
    expect(signal.maxFavorableMovePercent).toBe(5);
  });

  it('marks a signal STOP_HIT when stop is reached', async () => {
    const signal = await monitor.monitor(baseSignal, {
      ...baseSnapshot,
      lastPrice: 95,
      bestBid: 94.8,
      bestAsk: 95
    });

    expect(signal.status).toBe('STOP_HIT');
    expect(signal.statusReason).toBe('Stop loss reached');
    expect(signal.maxAdverseMovePercent).toBe(5);
  });
});
