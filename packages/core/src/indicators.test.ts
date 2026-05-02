import { describe, it, expect } from 'vitest';
import { BaseIndicatorAgent } from './indicators.js';
import { Candle } from './types.js';

describe('BaseIndicatorAgent', () => {
  const agent = new BaseIndicatorAgent();

  it('should calculate VWAP correctly', () => {
    const candles: Candle[] = [
      { ticker: 'A', timestamp: 0, open: 10, high: 12, low: 8, close: 10, volume: 100 },
      { ticker: 'A', timestamp: 1, open: 10, high: 15, low: 10, close: 14, volume: 200 }
    ];

    // Typical prices:
    // C1: (12 + 8 + 10) / 3 = 10
    // C2: (15 + 10 + 14) / 3 = 13
    
    // VWAP: (10 * 100 + 13 * 200) / (100 + 200) = (1000 + 2600) / 300 = 3600 / 300 = 12

    expect(agent.calculateVWAP(candles)).toBe(12);
  });

  it('should calculate spread percent correctly', () => {
    expect(agent.calculateSpreadPercent(99, 100)).toBe(1); // (100-99)/100 = 0.01 * 100 = 1%
    expect(agent.calculateSpreadPercent(0, 100)).toBe(0); // edge case
  });

  it('should calculate volume ratio correctly', () => {
    expect(agent.calculateVolumeRatio(250, 100)).toBe(2.5);
    expect(agent.calculateVolumeRatio(100, 0)).toBe(0); // edge case
  });

  it('should calculate order book imbalance correctly', () => {
    // Imbalance = (bidDepth - askDepth) / (bidDepth + askDepth)
    expect(agent.calculateOrderBookImbalance(60, 40)).toBe(0.2); // (60-40)/100
    expect(agent.calculateOrderBookImbalance(40, 60)).toBe(-0.2); // (40-60)/100
    expect(agent.calculateOrderBookImbalance(0, 0)).toBe(0); // edge case
  });
});
