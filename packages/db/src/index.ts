import { Candle, MarketSnapshot, Signal, SignalEvent, SignalOutcome, SignalStatus } from '@sentinel/core';

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

export function mapSignalToDbSignal(signal: Signal): DbSignal {
  const [entryZoneLow, entryZoneHigh] = signal.entryZone;

  return {
    id: signal.id,
    ticker: signal.ticker,
    strategy: signal.strategy,
    direction: signal.type,
    status: signal.status,
    entryZoneLow,
    entryZoneHigh,
    stopLoss: signal.stopLoss,
    target1: signal.targets[0],
    target2: signal.targets[1],
    confidence: optionalNumberFeature(signal.features, 'confidence'),
    validUntil: signal.validUntil,
    features: toJsonObject(signal.features),
    statusReason: signal.statusReason,
    latestPrice: signal.latestPrice,
    maxFavorableMovePercent: signal.maxFavorableMovePercent,
    maxAdverseMovePercent: signal.maxAdverseMovePercent,
    createdAt: signal.timestamp,
    updatedAt: signal.lastCheckedAt ?? signal.timestamp
  };
}

export function mapSignalEventToDbSignalEvent(event: SignalEvent): DbSignalEvent {
  return {
    id: event.id,
    signalId: event.signalId,
    previousStatus: event.previousStatus,
    newStatus: event.newStatus,
    reason: event.reason,
    latestPrice: event.latestPrice,
    eventTime: event.timestamp,
    createdAt: event.timestamp
  };
}

export function mapSignalOutcomeToDbSignalOutcome(outcome: SignalOutcome, signal: Signal): DbSignalOutcome {
  return {
    id: `outcome-${outcome.signalId}`,
    signalId: outcome.signalId,
    ticker: signal.ticker,
    strategy: signal.strategy,
    finalStatus: outcome.finalStatus,
    entryPrice: outcome.entryPrice,
    exitPrice: outcome.exitPrice,
    returnPercent: outcome.returnPercent,
    maxFavorableMovePercent: outcome.maxFavorableMovePercent,
    maxAdverseMovePercent: outcome.maxAdverseMovePercent,
    openedAt: outcome.openedAt,
    closedAt: outcome.closedAt,
    closeReason: outcome.closeReason,
    createdAt: outcome.closedAt
  };
}

export function mapMarketSnapshotToDbMarketSnapshot(snapshot: MarketSnapshot): DbMarketSnapshot {
  return {
    id: `snapshot-${snapshot.ticker}-${snapshot.timestamp}`,
    ticker: snapshot.ticker,
    snapshotTime: snapshot.timestamp,
    lastPrice: snapshot.lastPrice,
    bestBid: snapshot.bestBid,
    bestAsk: snapshot.bestAsk,
    bidDepth: snapshot.bidDepth,
    askDepth: snapshot.askDepth,
    volume: snapshot.volume,
    totalTurnover: snapshot.totalTurnover,
    metadata: {},
    createdAt: snapshot.timestamp
  };
}

export function mapCandleToDbCandle(candle: Candle, timeframe: string = '5m'): DbCandle {
  return {
    id: `candle-${candle.ticker}-${timeframe}-${candle.timestamp}`,
    ticker: candle.ticker,
    timeframe,
    candleTime: candle.timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
    vwap: candle.vwap,
    metadata: {},
    createdAt: candle.timestamp
  };
}

export type SupabaseRow = Record<string, JsonValue | undefined>;

export interface SupabaseResult<T = SupabaseRow> {
  data: T[] | T | null;
  error: { message: string } | null;
}

export interface SupabaseLikeQuery<T = SupabaseRow> {
  eq(column: string, value: unknown): SupabaseLikeQuery<T>;
  execute(): Promise<SupabaseResult<T>>;
  maybeSingle(): Promise<SupabaseResult<T>>;
}

export interface SupabaseLikeTable<T = SupabaseRow> {
  insert(values: T | T[]): Promise<SupabaseResult<T>>;
  update(values: Partial<T>): SupabaseLikeQuery<T>;
  select(columns?: string): SupabaseLikeQuery<T>;
}

export interface SupabaseLikeClient {
  from<T = SupabaseRow>(tableName: string): SupabaseLikeTable<T>;
}

export class SupabaseMarketSnapshotRepository implements MarketSnapshotRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async save(snapshot: DbMarketSnapshot): Promise<void> {
    await insertOrThrow(this.client, 'market_snapshots', dbMarketSnapshotToRow(snapshot));
  }

  async listByTicker(ticker: string): Promise<DbMarketSnapshot[]> {
    const result = await this.client
      .from<SupabaseRow>('market_snapshots')
      .select('*')
      .eq('ticker', ticker)
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbMarketSnapshot);
  }
}

export class SupabaseCandleRepository implements CandleRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async save(candle: DbCandle): Promise<void> {
    await insertOrThrow(this.client, 'candles', dbCandleToRow(candle));
  }

  async listByTicker(ticker: string): Promise<DbCandle[]> {
    const result = await this.client
      .from<SupabaseRow>('candles')
      .select('*')
      .eq('ticker', ticker)
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbCandle);
  }
}

export class SupabaseSignalRepository implements SignalRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async save(signal: DbSignal): Promise<void> {
    await insertOrThrow(this.client, 'signals', dbSignalToRow(signal));
  }

  async update(signal: DbSignal): Promise<void> {
    const result = await this.client
      .from<SupabaseRow>('signals')
      .update(dbSignalToRow(signal))
      .eq('id', signal.id)
      .execute();

    throwIfError(result);
  }

  async getById(signalId: string): Promise<DbSignal | null> {
    const result = await this.client
      .from<SupabaseRow>('signals')
      .select('*')
      .eq('id', signalId)
      .maybeSingle();

    throwIfError(result);
    return result.data ? rowToDbSignal(result.data as SupabaseRow) : null;
  }

  async listByTicker(ticker: string): Promise<DbSignal[]> {
    const result = await this.client
      .from<SupabaseRow>('signals')
      .select('*')
      .eq('ticker', ticker)
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbSignal);
  }

  async listActive(): Promise<DbSignal[]> {
    const result = await this.client
      .from<SupabaseRow>('signals')
      .select('*')
      .eq('status', 'ACTIVE')
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbSignal);
  }
}

export class SupabaseSignalEventRepository implements SignalEventRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async record(event: DbSignalEvent): Promise<void> {
    await insertOrThrow(this.client, 'signal_events', dbSignalEventToRow(event));
  }

  async listBySignal(signalId: string): Promise<DbSignalEvent[]> {
    const result = await this.client
      .from<SupabaseRow>('signal_events')
      .select('*')
      .eq('signal_id', signalId)
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbSignalEvent);
  }
}

export class SupabaseSignalOutcomeRepository implements SignalOutcomeRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async save(outcome: DbSignalOutcome): Promise<void> {
    await insertOrThrow(this.client, 'signal_outcomes', dbSignalOutcomeToRow(outcome));
  }

  async getBySignal(signalId: string): Promise<DbSignalOutcome | null> {
    const result = await this.client
      .from<SupabaseRow>('signal_outcomes')
      .select('*')
      .eq('signal_id', signalId)
      .maybeSingle();

    throwIfError(result);
    return result.data ? rowToDbSignalOutcome(result.data as SupabaseRow) : null;
  }

  async listByStrategy(strategy: string): Promise<DbSignalOutcome[]> {
    const result = await this.client
      .from<SupabaseRow>('signal_outcomes')
      .select('*')
      .eq('strategy', strategy)
      .execute();

    throwIfError(result);
    return rows(result).map(rowToDbSignalOutcome);
  }
}

export class SupabaseStrategyStatsRepository implements StrategyStatsRepository {
  constructor(private readonly client: SupabaseLikeClient) {}

  async save(stats: DbStrategyDailyStats): Promise<void> {
    await insertOrThrow(this.client, 'strategy_daily_stats', dbStrategyDailyStatsToRow(stats));
  }

  async getByStrategyAndDate(strategy: string, tradeDate: string): Promise<DbStrategyDailyStats | null> {
    const result = await this.client
      .from<SupabaseRow>('strategy_daily_stats')
      .select('*')
      .eq('strategy', strategy)
      .eq('trade_date', tradeDate)
      .maybeSingle();

    throwIfError(result);
    return result.data ? rowToDbStrategyDailyStats(result.data as SupabaseRow) : null;
  }
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

function optionalNumberFeature(features: Record<string, unknown>, key: string): number | undefined {
  const value = features[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function toJsonObject(value: Record<string, unknown>): JsonObject {
  return JSON.parse(JSON.stringify(value)) as JsonObject;
}

async function insertOrThrow(client: SupabaseLikeClient, tableName: string, row: SupabaseRow): Promise<void> {
  const result = await client.from<SupabaseRow>(tableName).insert(row);
  throwIfError(result);
}

function throwIfError(result: SupabaseResult): void {
  if (result.error) {
    throw new Error(result.error.message);
  }
}

function rows(result: SupabaseResult<SupabaseRow>): SupabaseRow[] {
  if (!result.data) return [];
  return Array.isArray(result.data) ? result.data : [result.data];
}

function dbMarketSnapshotToRow(snapshot: DbMarketSnapshot): SupabaseRow {
  return {
    id: snapshot.id,
    ticker: snapshot.ticker,
    snapshot_time: snapshot.snapshotTime,
    last_price: snapshot.lastPrice,
    best_bid: snapshot.bestBid,
    best_ask: snapshot.bestAsk,
    bid_depth: snapshot.bidDepth,
    ask_depth: snapshot.askDepth,
    volume: snapshot.volume,
    total_turnover: snapshot.totalTurnover,
    metadata: snapshot.metadata,
    created_at: snapshot.createdAt
  };
}

function rowToDbMarketSnapshot(row: SupabaseRow): DbMarketSnapshot {
  return {
    id: stringValue(row.id),
    ticker: stringValue(row.ticker),
    snapshotTime: numberValue(row.snapshot_time),
    lastPrice: numberValue(row.last_price),
    bestBid: numberValue(row.best_bid),
    bestAsk: numberValue(row.best_ask),
    bidDepth: numberValue(row.bid_depth),
    askDepth: numberValue(row.ask_depth),
    volume: numberValue(row.volume),
    totalTurnover: numberValue(row.total_turnover),
    metadata: jsonObjectValue(row.metadata),
    createdAt: numberValue(row.created_at)
  };
}

function dbCandleToRow(candle: DbCandle): SupabaseRow {
  return {
    id: candle.id,
    ticker: candle.ticker,
    timeframe: candle.timeframe,
    candle_time: candle.candleTime,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
    vwap: candle.vwap,
    metadata: candle.metadata,
    created_at: candle.createdAt
  };
}

function rowToDbCandle(row: SupabaseRow): DbCandle {
  return {
    id: stringValue(row.id),
    ticker: stringValue(row.ticker),
    timeframe: stringValue(row.timeframe),
    candleTime: numberValue(row.candle_time),
    open: numberValue(row.open),
    high: numberValue(row.high),
    low: numberValue(row.low),
    close: numberValue(row.close),
    volume: numberValue(row.volume),
    vwap: optionalNumberValue(row.vwap),
    metadata: jsonObjectValue(row.metadata),
    createdAt: numberValue(row.created_at)
  };
}

function dbSignalToRow(signal: DbSignal): SupabaseRow {
  return {
    id: signal.id,
    ticker: signal.ticker,
    strategy: signal.strategy,
    direction: signal.direction,
    status: signal.status,
    entry_zone_low: signal.entryZoneLow,
    entry_zone_high: signal.entryZoneHigh,
    stop_loss: signal.stopLoss,
    target1: signal.target1,
    target2: signal.target2,
    confidence: signal.confidence,
    valid_until: signal.validUntil,
    features: signal.features,
    status_reason: signal.statusReason,
    latest_price: signal.latestPrice,
    max_favorable_move_percent: signal.maxFavorableMovePercent,
    max_adverse_move_percent: signal.maxAdverseMovePercent,
    created_at: signal.createdAt,
    updated_at: signal.updatedAt
  };
}

function rowToDbSignal(row: SupabaseRow): DbSignal {
  return {
    id: stringValue(row.id),
    ticker: stringValue(row.ticker),
    strategy: stringValue(row.strategy),
    direction: stringValue(row.direction) as SignalDirection,
    status: stringValue(row.status) as SignalStatus,
    entryZoneLow: numberValue(row.entry_zone_low),
    entryZoneHigh: numberValue(row.entry_zone_high),
    stopLoss: numberValue(row.stop_loss),
    target1: optionalNumberValue(row.target1),
    target2: optionalNumberValue(row.target2),
    confidence: optionalNumberValue(row.confidence),
    validUntil: numberValue(row.valid_until),
    features: jsonObjectValue(row.features),
    statusReason: optionalStringValue(row.status_reason),
    latestPrice: optionalNumberValue(row.latest_price),
    maxFavorableMovePercent: optionalNumberValue(row.max_favorable_move_percent),
    maxAdverseMovePercent: optionalNumberValue(row.max_adverse_move_percent),
    createdAt: numberValue(row.created_at),
    updatedAt: numberValue(row.updated_at)
  };
}

function dbSignalEventToRow(event: DbSignalEvent): SupabaseRow {
  return {
    id: event.id,
    signal_id: event.signalId,
    previous_status: event.previousStatus,
    new_status: event.newStatus,
    reason: event.reason,
    latest_price: event.latestPrice,
    event_time: event.eventTime,
    created_at: event.createdAt
  };
}

function rowToDbSignalEvent(row: SupabaseRow): DbSignalEvent {
  return {
    id: stringValue(row.id),
    signalId: stringValue(row.signal_id),
    previousStatus: stringValue(row.previous_status) as SignalStatus,
    newStatus: stringValue(row.new_status) as SignalStatus,
    reason: stringValue(row.reason),
    latestPrice: numberValue(row.latest_price),
    eventTime: numberValue(row.event_time),
    createdAt: numberValue(row.created_at)
  };
}

function dbSignalOutcomeToRow(outcome: DbSignalOutcome): SupabaseRow {
  return {
    id: outcome.id,
    signal_id: outcome.signalId,
    ticker: outcome.ticker,
    strategy: outcome.strategy,
    final_status: outcome.finalStatus,
    entry_price: outcome.entryPrice,
    exit_price: outcome.exitPrice,
    return_percent: outcome.returnPercent,
    max_favorable_move_percent: outcome.maxFavorableMovePercent,
    max_adverse_move_percent: outcome.maxAdverseMovePercent,
    opened_at: outcome.openedAt,
    closed_at: outcome.closedAt,
    close_reason: outcome.closeReason,
    created_at: outcome.createdAt
  };
}

function rowToDbSignalOutcome(row: SupabaseRow): DbSignalOutcome {
  return {
    id: stringValue(row.id),
    signalId: stringValue(row.signal_id),
    ticker: stringValue(row.ticker),
    strategy: stringValue(row.strategy),
    finalStatus: stringValue(row.final_status) as SignalStatus,
    entryPrice: numberValue(row.entry_price),
    exitPrice: numberValue(row.exit_price),
    returnPercent: numberValue(row.return_percent),
    maxFavorableMovePercent: numberValue(row.max_favorable_move_percent),
    maxAdverseMovePercent: numberValue(row.max_adverse_move_percent),
    openedAt: numberValue(row.opened_at),
    closedAt: numberValue(row.closed_at),
    closeReason: stringValue(row.close_reason),
    createdAt: numberValue(row.created_at)
  };
}

function dbStrategyDailyStatsToRow(stats: DbStrategyDailyStats): SupabaseRow {
  return {
    id: stats.id,
    strategy: stats.strategy,
    trade_date: stats.tradeDate,
    signals_generated: stats.signalsGenerated,
    wins: stats.wins,
    losses: stats.losses,
    expired: stats.expired,
    invalidated: stats.invalidated,
    total_return_percent: stats.totalReturnPercent,
    metadata: stats.metadata,
    created_at: stats.createdAt,
    updated_at: stats.updatedAt
  };
}

function rowToDbStrategyDailyStats(row: SupabaseRow): DbStrategyDailyStats {
  return {
    id: stringValue(row.id),
    strategy: stringValue(row.strategy),
    tradeDate: stringValue(row.trade_date),
    signalsGenerated: numberValue(row.signals_generated),
    wins: numberValue(row.wins),
    losses: numberValue(row.losses),
    expired: numberValue(row.expired),
    invalidated: numberValue(row.invalidated),
    totalReturnPercent: numberValue(row.total_return_percent),
    metadata: jsonObjectValue(row.metadata),
    createdAt: numberValue(row.created_at),
    updatedAt: numberValue(row.updated_at)
  };
}

function stringValue(value: JsonValue | undefined): string {
  return typeof value === 'string' ? value : String(value ?? '');
}

function optionalStringValue(value: JsonValue | undefined): string | undefined {
  return value === undefined || value === null ? undefined : stringValue(value);
}

function numberValue(value: JsonValue | undefined): number {
  return typeof value === 'number' ? value : Number(value ?? 0);
}

function optionalNumberValue(value: JsonValue | undefined): number | undefined {
  if (value === undefined || value === null) return undefined;
  return numberValue(value);
}

function jsonObjectValue(value: JsonValue | undefined): JsonObject {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value;
  }

  return {};
}
