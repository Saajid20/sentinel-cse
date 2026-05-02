import { Candle, CandleAgent, MarketSnapshot } from './types.js';

export class BasicCandleAgent implements CandleAgent {
  private candles: Map<string, Candle[]> = new Map();
  private currentCandle: Map<string, Candle> = new Map();
  private intervalMs: number;

  constructor(intervalMs: number = 5 * 60 * 1000) {
    this.intervalMs = intervalMs;
  }

  process(snapshot: MarketSnapshot): Candle | null {
    const { ticker, timestamp, lastPrice, volume } = snapshot;
    const currentPeriod = Math.floor(timestamp / this.intervalMs) * this.intervalMs;

    let activeCandle = this.currentCandle.get(ticker);

    if (!activeCandle) {
      activeCandle = {
        ticker,
        timestamp: currentPeriod,
        open: lastPrice,
        high: lastPrice,
        low: lastPrice,
        close: lastPrice,
        volume: volume
      };
      this.currentCandle.set(ticker, activeCandle);
      return null;
    }

    if (timestamp >= activeCandle.timestamp + this.intervalMs) {
      // Close the current candle
      const finishedCandle = { ...activeCandle };
      
      const history = this.candles.get(ticker) || [];
      history.push(finishedCandle);
      this.candles.set(ticker, history);

      // Start new candle
      activeCandle = {
        ticker,
        timestamp: currentPeriod,
        open: lastPrice,
        high: lastPrice,
        low: lastPrice,
        close: lastPrice,
        volume: volume
      };
      this.currentCandle.set(ticker, activeCandle);

      return finishedCandle;
    } else {
      // Update existing candle
      activeCandle.high = Math.max(activeCandle.high, lastPrice);
      activeCandle.low = Math.min(activeCandle.low, lastPrice);
      activeCandle.close = lastPrice;
      activeCandle.volume += volume;
      return null; // Candle not yet closed
    }
  }

  getCandles(ticker: string): Candle[] {
    return this.candles.get(ticker) || [];
  }
}
