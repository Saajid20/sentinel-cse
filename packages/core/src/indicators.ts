import { Candle, IndicatorAgent } from './types.js';

export class BaseIndicatorAgent implements IndicatorAgent {
  calculateVWAP(candles: Candle[]): number {
    if (candles.length === 0) return 0;
    let cumulativeTypicalPriceVolume = 0;
    let cumulativeVolume = 0;

    for (const candle of candles) {
      const typicalPrice = (candle.high + candle.low + candle.close) / 3;
      cumulativeTypicalPriceVolume += typicalPrice * candle.volume;
      cumulativeVolume += candle.volume;
    }

    if (cumulativeVolume === 0) return 0;
    return cumulativeTypicalPriceVolume / cumulativeVolume;
  }

  calculateSpreadPercent(bid: number, ask: number): number {
    if (bid === 0 || ask === 0) return 0;
    const spread = ask - bid;
    return (spread / ask) * 100;
  }

  calculateVolumeRatio(currentVolume: number, averageVolume: number): number {
    if (averageVolume === 0) return 0;
    return currentVolume / averageVolume;
  }

  calculateOrderBookImbalance(bidDepth: number, askDepth: number): number {
    const totalDepth = bidDepth + askDepth;
    if (totalDepth === 0) return 0;
    return (bidDepth - askDepth) / totalDepth;
  }
}
