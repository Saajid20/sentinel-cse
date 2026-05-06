import { describe, it, expect } from 'vitest';
import { OpeningMomentumDetector } from './openingMomentum.js';
import { MarketSnapshot, Candle } from '@sentinel/core';

describe('OpeningMomentumDetector', () => {
  const createDetector = (parameters = {}) => {
    const detector = new OpeningMomentumDetector(parameters);
    detector.averageVolumeMap['SAMP.N0000'] = 100;
    return detector;
  };

  const snapshot: MarketSnapshot = {
    ticker: 'SAMP.N0000',
    timestamp: 1000000,
    lastPrice: 55,
    bestBid: 54.5,
    bestAsk: 55,
    bidDepth: 200,
    askDepth: 100,
    volume: 300,
    totalTurnover: 16500
  };

  const candles: Candle[] = [
    {
      ticker: 'SAMP.N0000',
      timestamp: 0,
      open: 50,
      high: 52,
      low: 50,
      close: 51,
      volume: 1000
    }
  ];

  it('should detect a valid setup with default parameters', async () => {
    const detector = createDetector();
    const signal = await detector.detect(snapshot, candles);

    expect(signal).not.toBeNull();
    expect(signal?.type).toBe('BUY_WATCH');
    expect(signal?.strategy).toBe('CSE_OPENING_MOMENTUM_V1');
    expect(signal?.stopLoss).toBe(50.49);
    expect(signal?.validUntil).toBe(1600000);
    expect(signal?.features?.vwapDistancePercent).toBeCloseTo(7.8431372549019605);
  });

  it('should reject if spread is too wide', async () => {
    const detector = createDetector();

    const snapshot: MarketSnapshot = {
      ticker: 'SAMP.N0000',
      timestamp: 1000000,
      lastPrice: 55,
      bestBid: 53,
      bestAsk: 55, // Spread = 2, Spread % = 2 / 55 = ~3.6% (> 1.5%)
      bidDepth: 200,
      askDepth: 100,
      volume: 300,
      totalTurnover: 16500
    };
    const candles: Candle[] = [
      { ticker: 'SAMP.N0000', timestamp: 0, open: 50, high: 52, low: 50, close: 51, volume: 1000 }
    ];

    const signal = await detector.detect(snapshot, candles);
    expect(signal).toBeNull();
  });

  it('should reject when a custom spread threshold is exceeded', async () => {
    const detector = createDetector({ spreadPercentThreshold: 0.8 });

    const signal = await detector.detect(snapshot, candles);

    expect(signal).toBeNull();
  });

  it('should reject when volume ratio is below a custom threshold', async () => {
    const detector = createDetector({ volumeRatioThreshold: 3.5 });

    const signal = await detector.detect(snapshot, candles);

    expect(signal).toBeNull();
  });

  it('should reject when order-book imbalance is below a custom threshold', async () => {
    const detector = createDetector({ orderBookImbalanceThreshold: 0.4 });

    const signal = await detector.detect(snapshot, candles);

    expect(signal).toBeNull();
  });

  it('should use a custom strategy name in generated signals', async () => {
    const detector = createDetector({ strategyName: 'CSE_OPENING_MOMENTUM_TEST' });

    const signal = await detector.detect(snapshot, candles);

    expect(signal).not.toBeNull();
    expect(signal?.strategy).toBe('CSE_OPENING_MOMENTUM_TEST');
  });

  it('should reject an overextended signal when max VWAP distance is configured', async () => {
    const detector = createDetector({ maxVwapDistancePercent: 5 });

    const signal = await detector.detect(snapshot, candles);

    expect(signal).toBeNull();
  });
});
