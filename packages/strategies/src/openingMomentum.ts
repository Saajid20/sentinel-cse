import {
  Candle,
  MarketSnapshot,
  Signal,
  SetupDetectorAgent
} from '@sentinel/core';
import { BaseIndicatorAgent } from '@sentinel/core';

export type OpeningMomentumParameters = {
  strategyName: string;
  spreadPercentThreshold: number;
  volumeRatioThreshold: number;
  orderBookImbalanceThreshold: number;
  stopLossBufferPercent: number;
  maxVwapDistancePercent?: number;
  validityMinutes?: number;
};

export const DEFAULT_OPENING_MOMENTUM_PARAMETERS: OpeningMomentumParameters = {
  strategyName: 'CSE_OPENING_MOMENTUM_V1',
  spreadPercentThreshold: 1.5,
  volumeRatioThreshold: 2,
  orderBookImbalanceThreshold: 0,
  stopLossBufferPercent: 1,
  validityMinutes: 10
};

export class OpeningMomentumDetector implements SetupDetectorAgent {
  private indicators = new BaseIndicatorAgent();
  private parameters: OpeningMomentumParameters;

  // Mocks for condition checks that aren't fully implemented yet
  public aspiKillSwitchActive = false;
  public nearUpperPriceBand = false;

  // Need to know average volume, we'll mock it or pass it in
  public averageVolumeMap: Record<string, number> = {};

  constructor(parameters: Partial<OpeningMomentumParameters> = {}) {
    this.parameters = {
      ...DEFAULT_OPENING_MOMENTUM_PARAMETERS,
      ...parameters
    };
  }

  async detect(
    snapshot: MarketSnapshot,
    candles: Candle[],
    indicatorsMock?: any
  ): Promise<Partial<Signal> | null> {
    if (candles.length === 0) return null;

    if (this.aspiKillSwitchActive) return null;
    if (this.nearUpperPriceBand) return null;

    // Calculate indicators
    const vwap = this.indicators.calculateVWAP(candles);
    const spreadPercent = this.indicators.calculateSpreadPercent(snapshot.bestBid, snapshot.bestAsk);

    const avgVolume = this.averageVolumeMap[snapshot.ticker] || 1000;
    const volumeRatio = this.indicators.calculateVolumeRatio(snapshot.volume, avgVolume);

    const orderBookImbalance = this.indicators.calculateOrderBookImbalance(snapshot.bidDepth, snapshot.askDepth);

    // Rule 1: Price above VWAP
    if (snapshot.lastPrice <= vwap) return null;

    const vwapDistancePercent =
      vwap > 0 ? ((snapshot.lastPrice - vwap) / vwap) * 100 : Number.POSITIVE_INFINITY;

    if (
      this.parameters.maxVwapDistancePercent !== undefined &&
      vwapDistancePercent > this.parameters.maxVwapDistancePercent
    ) {
      return null;
    }

    // Rule 2: Price breaks first 5-minute high
    // Assuming first candle in array is the first 5-minute candle
    const first5MinHigh = candles[0].high;
    if (snapshot.lastPrice <= first5MinHigh) return null;

    // Rule 3: Volume ratio > 2
    if (volumeRatio <= this.parameters.volumeRatioThreshold) return null;

    // Rule 4: Spread < 1.5%
    if (spreadPercent >= this.parameters.spreadPercentThreshold) return null;

    // Rule 5: Bid depth stronger than ask depth (imbalance > 0)
    if (orderBookImbalance <= this.parameters.orderBookImbalanceThreshold) return null;

    // All conditions met, generate setup
    return {
      ticker: snapshot.ticker,
      strategy: this.parameters.strategyName,
      timestamp: snapshot.timestamp,
      type: 'BUY_WATCH',
      entryZone: [snapshot.lastPrice * 0.99, snapshot.lastPrice * 1.01],
      stopLoss:
        Math.min(first5MinHigh, vwap) * (1 - this.parameters.stopLossBufferPercent / 100),
      targets: [snapshot.lastPrice * 1.05, snapshot.lastPrice * 1.10],
      validUntil:
        snapshot.timestamp + (this.parameters.validityMinutes ?? 10) * 60 * 1000,
      features: {
        vwap,
        vwapDistancePercent,
        spreadPercent,
        volumeRatio,
        orderBookImbalance,
        first5MinHigh
      }
    };
  }
}
