import { BaseIndicatorAgent } from './indicators.js';
import { MarketSnapshot, MonitorAgent, Signal, SignalStatus } from './types.js';

const DEFAULT_OPENING_MOMENTUM_VALIDITY_MS = 10 * 60 * 1000;
const SPREAD_INVALIDATION_PERCENT = 2;

export class BasicMonitorAgent implements MonitorAgent {
  private indicators = new BaseIndicatorAgent();

  async monitor(signal: Signal, snapshot: MarketSnapshot): Promise<Signal> {
    const trackedSignal = this.withTracking(signal, snapshot);

    if (this.isTerminal(signal.status)) {
      return trackedSignal;
    }

    const target = this.reachedTarget(signal, snapshot.lastPrice);
    if (target !== null) {
      return this.withStatus(trackedSignal, 'TARGET_HIT', `Target ${target} reached`);
    }

    if (this.reachedStop(signal, snapshot.lastPrice)) {
      return this.withStatus(trackedSignal, 'STOP_HIT', 'Stop loss reached');
    }

    if (snapshot.timestamp > this.validUntil(signal)) {
      return this.withStatus(trackedSignal, 'EXPIRED', 'Signal validity window elapsed');
    }

    const vwap = this.getVWAP(signal);
    if (vwap !== null && snapshot.lastPrice < vwap) {
      return this.withStatus(trackedSignal, 'INVALIDATED', 'Price fell below VWAP');
    }

    const spreadPercent = this.indicators.calculateSpreadPercent(snapshot.bestBid, snapshot.bestAsk);
    if (spreadPercent > SPREAD_INVALIDATION_PERCENT) {
      return this.withStatus(trackedSignal, 'INVALIDATED', 'Spread exceeded 2%');
    }

    if (!this.isInsideEntryZone(signal, snapshot.lastPrice)) {
      return this.withStatus(trackedSignal, 'INVALIDATED', 'Price left entry zone before entry');
    }

    return this.withStatus(trackedSignal, 'ACTIVE', 'Signal remains valid');
  }

  private withTracking(signal: Signal, snapshot: MarketSnapshot): Signal {
    const move = this.calculateMovePercent(signal, snapshot.lastPrice);
    const maxFavorableMovePercent = Math.max(signal.maxFavorableMovePercent ?? 0, move.favorable);
    const maxAdverseMovePercent = Math.max(signal.maxAdverseMovePercent ?? 0, move.adverse);

    return {
      ...signal,
      maxFavorableMovePercent,
      maxAdverseMovePercent,
      latestPrice: snapshot.lastPrice,
      lastCheckedAt: snapshot.timestamp
    };
  }

  private withStatus(signal: Signal, status: SignalStatus, statusReason: string): Signal {
    return {
      ...signal,
      status,
      statusReason
    };
  }

  private isTerminal(status: SignalStatus): boolean {
    return status !== 'ACTIVE';
  }

  private validUntil(signal: Signal): number {
    if (Number.isFinite(signal.validUntil)) return signal.validUntil;

    return signal.timestamp + DEFAULT_OPENING_MOMENTUM_VALIDITY_MS;
  }

  private getVWAP(signal: Signal): number | null {
    const vwap = signal.features['vwap'];
    return typeof vwap === 'number' && Number.isFinite(vwap) ? vwap : null;
  }

  private isInsideEntryZone(signal: Signal, price: number): boolean {
    const [low, high] = signal.entryZone;
    return price >= low && price <= high;
  }

  private reachedTarget(signal: Signal, price: number): number | null {
    const targets = signal.targets.slice(0, 2);
    if (this.isShortSignal(signal)) {
      return targets.find((target) => price <= target) ?? null;
    }

    return targets.find((target) => price >= target) ?? null;
  }

  private reachedStop(signal: Signal, price: number): boolean {
    return this.isShortSignal(signal) ? price >= signal.stopLoss : price <= signal.stopLoss;
  }

  private calculateMovePercent(signal: Signal, price: number): { favorable: number; adverse: number } {
    const referencePrice = this.referencePrice(signal);
    if (referencePrice <= 0) return { favorable: 0, adverse: 0 };

    const rawMovePercent = ((price - referencePrice) / referencePrice) * 100;
    const directionalMove = this.isShortSignal(signal) ? -rawMovePercent : rawMovePercent;

    return {
      favorable: Math.max(0, directionalMove),
      adverse: Math.max(0, -directionalMove)
    };
  }

  private referencePrice(signal: Signal): number {
    const [low, high] = signal.entryZone;
    return (low + high) / 2;
  }

  private isShortSignal(signal: Signal): boolean {
    return signal.type === 'SELL' || signal.type === 'SELL_WATCH';
  }
}
