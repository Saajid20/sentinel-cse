import { SignalStatus } from '@sentinel/core';

export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export type SignalDirection = 'BUY_WATCH' | 'SELL_WATCH' | 'BUY' | 'SELL';

export interface DbMarketSnapshot {
  id: string;
  ticker: string;
  snapshotTime: number;
  lastPrice: number;
  bestBid: number;
  bestAsk: number;
  bidDepth: number;
  askDepth: number;
  volume: number;
  totalTurnover: number;
  metadata: JsonObject;
  createdAt: number;
}

export interface DbCandle {
  id: string;
  ticker: string;
  timeframe: string;
  candleTime: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
  metadata: JsonObject;
  createdAt: number;
}

export interface DbSignal {
  id: string;
  ticker: string;
  strategy: string;
  direction: SignalDirection;
  status: SignalStatus;
  entryZoneLow: number;
  entryZoneHigh: number;
  stopLoss: number;
  target1?: number;
  target2?: number;
  confidence?: number;
  validUntil: number;
  features: JsonObject;
  statusReason?: string;
  latestPrice?: number;
  maxFavorableMovePercent?: number;
  maxAdverseMovePercent?: number;
  createdAt: number;
  updatedAt: number;
}

export interface DbSignalEvent {
  id: string;
  signalId: string;
  previousStatus: SignalStatus;
  newStatus: SignalStatus;
  reason: string;
  latestPrice: number;
  eventTime: number;
  createdAt: number;
}

export interface DbSignalOutcome {
  id: string;
  signalId: string;
  ticker: string;
  strategy: string;
  finalStatus: SignalStatus;
  entryPrice: number;
  exitPrice: number;
  returnPercent: number;
  maxFavorableMovePercent: number;
  maxAdverseMovePercent: number;
  openedAt: number;
  closedAt: number;
  closeReason: string;
  createdAt: number;
}

export interface DbStrategyDailyStats {
  id: string;
  strategy: string;
  tradeDate: string;
  signalsGenerated: number;
  wins: number;
  losses: number;
  expired: number;
  invalidated: number;
  totalReturnPercent: number;
  metadata: JsonObject;
  createdAt: number;
  updatedAt: number;
}

export interface MarketSnapshotRepository {
  save(snapshot: DbMarketSnapshot): Promise<void>;
  listByTicker(ticker: string): Promise<DbMarketSnapshot[]>;
}

export interface CandleRepository {
  save(candle: DbCandle): Promise<void>;
  listByTicker(ticker: string): Promise<DbCandle[]>;
}

export interface SignalRepository {
  save(signal: DbSignal): Promise<void>;
  update(signal: DbSignal): Promise<void>;
  getById(signalId: string): Promise<DbSignal | null>;
  listByTicker(ticker: string): Promise<DbSignal[]>;
  listActive(): Promise<DbSignal[]>;
}

export interface SignalEventRepository {
  record(event: DbSignalEvent): Promise<void>;
  listBySignal(signalId: string): Promise<DbSignalEvent[]>;
}

export interface SignalOutcomeRepository {
  save(outcome: DbSignalOutcome): Promise<void>;
  getBySignal(signalId: string): Promise<DbSignalOutcome | null>;
  listByStrategy(strategy: string): Promise<DbSignalOutcome[]>;
}

export interface StrategyStatsRepository {
  save(stats: DbStrategyDailyStats): Promise<void>;
  getByStrategyAndDate(strategy: string, tradeDate: string): Promise<DbStrategyDailyStats | null>;
}

export interface DbRepositories {
  marketSnapshots: MarketSnapshotRepository;
  candles: CandleRepository;
  signals: SignalRepository;
  signalEvents: SignalEventRepository;
  signalOutcomes: SignalOutcomeRepository;
  strategyStats: StrategyStatsRepository;
}

export class InMemoryDbAdapter implements DbRepositories {
  public readonly marketSnapshots: MarketSnapshotRepository;
  public readonly candles: CandleRepository;
  public readonly signals: SignalRepository;
  public readonly signalEvents: SignalEventRepository;
  public readonly signalOutcomes: SignalOutcomeRepository;
  public readonly strategyStats: StrategyStatsRepository;

  private marketSnapshotRows = new Map<string, DbMarketSnapshot>();
  private candleRows = new Map<string, DbCandle>();
  private signalRows = new Map<string, DbSignal>();
  private signalEventRows: DbSignalEvent[] = [];
  private signalOutcomeRows = new Map<string, DbSignalOutcome>();
  private strategyStatsRows = new Map<string, DbStrategyDailyStats>();

  constructor() {
    this.marketSnapshots = {
      save: async (snapshot) => {
        this.marketSnapshotRows.set(snapshot.id, clone(snapshot));
      },
      listByTicker: async (ticker) =>
        Array.from(this.marketSnapshotRows.values())
          .filter((snapshot) => snapshot.ticker === ticker)
          .map(clone)
    };

    this.candles = {
      save: async (candle) => {
        this.candleRows.set(candle.id, clone(candle));
      },
      listByTicker: async (ticker) =>
        Array.from(this.candleRows.values())
          .filter((candle) => candle.ticker === ticker)
          .map(clone)
    };

    this.signals = {
      save: async (signal) => {
        this.signalRows.set(signal.id, clone(signal));
      },
      update: async (signal) => {
        this.signalRows.set(signal.id, clone(signal));
      },
      getById: async (signalId) => {
        const signal = this.signalRows.get(signalId);
        return signal ? clone(signal) : null;
      },
      listByTicker: async (ticker) =>
        Array.from(this.signalRows.values())
          .filter((signal) => signal.ticker === ticker)
          .map(clone),
      listActive: async () =>
        Array.from(this.signalRows.values())
          .filter((signal) => signal.status === 'ACTIVE')
          .map(clone)
    };

    this.signalEvents = {
      record: async (event) => {
        this.signalEventRows.push(clone(event));
      },
      listBySignal: async (signalId) =>
        this.signalEventRows
          .filter((event) => event.signalId === signalId)
          .map(clone)
    };

    this.signalOutcomes = {
      save: async (outcome) => {
        this.signalOutcomeRows.set(outcome.signalId, clone(outcome));
      },
      getBySignal: async (signalId) => {
        const outcome = this.signalOutcomeRows.get(signalId);
        return outcome ? clone(outcome) : null;
      },
      listByStrategy: async (strategy) =>
        Array.from(this.signalOutcomeRows.values())
          .filter((outcome) => outcome.strategy === strategy)
          .map(clone)
    };

    this.strategyStats = {
      save: async (stats) => {
        this.strategyStatsRows.set(statsKey(stats.strategy, stats.tradeDate), clone(stats));
      },
      getByStrategyAndDate: async (strategy, tradeDate) => {
        const stats = this.strategyStatsRows.get(statsKey(strategy, tradeDate));
        return stats ? clone(stats) : null;
      }
    };
  }
}

function statsKey(strategy: string, tradeDate: string): string {
  return `${strategy}:${tradeDate}`;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}
