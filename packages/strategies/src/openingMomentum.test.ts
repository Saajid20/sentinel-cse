import { describe, it, expect } from 'vitest';
import { OpeningMomentumDetector } from './openingMomentum.js';
import { MarketSnapshot, Candle } from '@sentinel/core';

describe('OpeningMomentumDetector', () => {
  it('should detect a valid setup', async () => {
    const detector = new OpeningMomentumDetector();
    
    // Setup environment
    detector.averageVolumeMap['SAMP.N0000'] = 100;
    
    const snapshot: MarketSnapshot = {
      ticker: 'SAMP.N0000',
      timestamp: 1000000,
      lastPrice: 55,
      bestBid: 54.5,
      bestAsk: 55, // Spread = 0.5, Spread % = 0.5 / 55 = ~0.9% (< 1.5%)
      bidDepth: 200,
      askDepth: 100, // Bid > Ask
      volume: 300, // Volume ratio = 300 / 100 = 3 (> 2)
      totalTurnover: 16500
    };
    
    const candles: Candle[] = [
      { ticker: 'SAMP.N0000', timestamp: 0, open: 50, high: 52, low: 50, close: 51, volume: 1000 }
      // first5MinHigh = 52. 
      // lastPrice = 55 (55 > 52)
      // vwap = 51 (typical = (52+50+51)/3 = 51)
      // lastPrice > vwap (55 > 51)
    ];

    const signal = await detector.detect(snapshot, candles);
    
    expect(signal).not.toBeNull();
    expect(signal?.type).toBe('BUY_WATCH');
    expect(signal?.strategy).toBe('CSE_OPENING_MOMENTUM_V1');
  });

  it('should reject if spread is too wide', async () => {
    const detector = new OpeningMomentumDetector();
    detector.averageVolumeMap['SAMP.N0000'] = 100;
    
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
});
