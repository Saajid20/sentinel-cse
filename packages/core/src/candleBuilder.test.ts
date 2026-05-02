import { describe, it, expect } from 'vitest';
import { BasicCandleAgent } from './candleBuilder.js';

describe('BasicCandleAgent', () => {
  it('should build candles from snapshots', () => {
    const agent = new BasicCandleAgent(60000); // 1 minute interval

    const snap1 = {
      ticker: 'SAMP.N0000',
      timestamp: 100000,
      lastPrice: 50,
      bestBid: 49,
      bestAsk: 51,
      bidDepth: 100,
      askDepth: 100,
      volume: 100,
      totalTurnover: 5000
    };

    const snap2 = {
      ...snap1,
      timestamp: 120000,
      lastPrice: 52,
      volume: 200
    };

    const snap3 = {
      ...snap1,
      timestamp: 160000, // Still in same 1-min interval as snap2 (120000-180000)
      lastPrice: 51,
      volume: 150
    };
    
    const snap4 = {
        ...snap1,
        timestamp: 190000, // new candle
        lastPrice: 53,
        volume: 300
    };

    // First snapshot starts a candle but doesn't complete it
    expect(agent.process(snap1)).toBeNull();
    
    // Second snapshot completes the first candle (timestamp crosses boundary)
    const candle1 = agent.process(snap2);
    expect(candle1).not.toBeNull();
    expect(candle1?.open).toBe(50);
    expect(candle1?.high).toBe(50);
    expect(candle1?.close).toBe(50);
    expect(candle1?.volume).toBe(100);

    // Third snapshot updates the current candle
    expect(agent.process(snap3)).toBeNull();

    // Fourth snapshot completes the second candle
    const candle2 = agent.process(snap4);
    expect(candle2).not.toBeNull();
    expect(candle2?.open).toBe(52);
    expect(candle2?.high).toBe(52);
    expect(candle2?.low).toBe(51);
    expect(candle2?.close).toBe(51);
    expect(candle2?.volume).toBe(350); // 200 + 150

    // Get all candles
    const history = agent.getCandles('SAMP.N0000');
    expect(history.length).toBe(2);
  });
});
