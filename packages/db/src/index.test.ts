import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { Candle, MarketSnapshot, Signal, SignalEvent, SignalOutcome } from '@sentinel/core';
import {
  DbSignal,
  DbSignalEvent,
  DbSignalOutcome,
  InMemoryDbAdapter,
  mapCandleToDbCandle,
  mapMarketSnapshotToDbMarketSnapshot,
  mapSignalEventToDbSignalEvent,
  mapSignalOutcomeToDbSignalOutcome,
  mapSignalToDbSignal,
  SupabaseLikeClient,
  SupabaseLikeQuery,
  SupabaseLikeTable,
  SupabaseMarketSnapshotRepository,
  SupabaseResult,
  SupabaseRow,
  SupabaseSignalEventRepository,
  SupabaseSignalOutcomeRepository,
  SupabaseSignalRepository
} from './index.js';

const now = Date.UTC(2026, 0, 1, 4, 30);

const makeSignal = (overrides: Partial<DbSignal> = {}): DbSignal => ({
  id: 'sig-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  direction: 'BUY_WATCH',
  status: 'ACTIVE',
  entryZoneLow: 99,
  entryZoneHigh: 101,
  stopLoss: 95,
  target1: 105,
  target2: 110,
  confidence: 72.5,
  validUntil: now + 10 * 60 * 1000,
  features: {
    vwap: 98,
    volumeRatio: 3
  },
  statusReason: 'Signal generated',
  latestPrice: 100,
  maxFavorableMovePercent: 0,
  maxAdverseMovePercent: 0,
  createdAt: now,
  updatedAt: now,
  ...overrides
});

const makeEvent = (overrides: Partial<DbSignalEvent> = {}): DbSignalEvent => ({
  id: 'event-1',
  signalId: 'sig-1',
  previousStatus: 'ACTIVE',
  newStatus: 'INVALIDATED',
  reason: 'Price fell below VWAP',
  latestPrice: 97,
  eventTime: now + 60_000,
  createdAt: now + 60_000,
  ...overrides
});

const makeOutcome = (overrides: Partial<DbSignalOutcome> = {}): DbSignalOutcome => ({
  id: 'outcome-1',
  signalId: 'sig-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  finalStatus: 'TARGET_HIT',
  entryPrice: 100,
  exitPrice: 105,
  returnPercent: 5,
  maxFavorableMovePercent: 5,
  maxAdverseMovePercent: 1,
  openedAt: now,
  closedAt: now + 120_000,
  closeReason: 'Target 105 reached',
  createdAt: now + 120_000,
  ...overrides
});

describe('InMemoryDbAdapter repositories', () => {
  it('saves and retrieves signals through the repository interface', async () => {
    const db = new InMemoryDbAdapter();
    const signal = makeSignal();

    await db.signals.save(signal);

    await expect(db.signals.getById('sig-1')).resolves.toEqual(signal);
    await expect(db.signals.getById('missing')).resolves.toBeNull();
    await expect(db.signals.listByTicker('SAMP.N0000')).resolves.toEqual([signal]);
  });

  it('records signal events', async () => {
    const db = new InMemoryDbAdapter();
    const event = makeEvent();

    await db.signalEvents.record(event);

    await expect(db.signalEvents.listBySignal('sig-1')).resolves.toEqual([event]);
  });

  it('stores signal outcomes with strategy directly on the outcome', async () => {
    const db = new InMemoryDbAdapter();
    const outcome = makeOutcome({ strategy: 'CSE_OPENING_MOMENTUM_V1' });

    await db.signalOutcomes.save(outcome);

    await expect(db.signalOutcomes.getBySignal('sig-1')).resolves.toEqual(outcome);
    await expect(db.signalOutcomes.listByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toEqual([outcome]);
  });

  it('lists active signals', async () => {
    const db = new InMemoryDbAdapter();
    const activeSignal = makeSignal({ id: 'active' });
    const expiredSignal = makeSignal({ id: 'expired', status: 'EXPIRED' });

    await db.signals.save(activeSignal);
    await db.signals.save(expiredSignal);

    await expect(db.signals.listActive()).resolves.toEqual([activeSignal]);
  });

  it('lists outcomes by strategy', async () => {
    const db = new InMemoryDbAdapter();
    const openingOutcome = makeOutcome({ id: 'opening-outcome', signalId: 'opening' });
    const otherOutcome = makeOutcome({
      id: 'other-outcome',
      signalId: 'other',
      strategy: 'OTHER_STRATEGY',
      finalStatus: 'STOP_HIT',
      closeReason: 'Stop loss reached'
    });

    await db.signalOutcomes.save(openingOutcome);
    await db.signalOutcomes.save(otherOutcome);

    await expect(db.signalOutcomes.listByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toEqual([openingOutcome]);
    await expect(db.signalOutcomes.listByStrategy('OTHER_STRATEGY')).resolves.toEqual([otherOutcome]);
  });
});

describe('initial SQL migration', () => {
  it('exists and includes all required tables', () => {
    const migration = readFileSync('packages/db/migrations/001_initial_schema.sql', 'utf8').toLowerCase();

    expect(migration).toContain('create table if not exists market_snapshots');
    expect(migration).toContain('create table if not exists candles');
    expect(migration).toContain('create table if not exists signals');
    expect(migration).toContain('create table if not exists signal_events');
    expect(migration).toContain('create table if not exists signal_outcomes');
    expect(migration).toContain('create table if not exists strategy_daily_stats');
  });
});

const makeCoreSignal = (overrides: Partial<Signal> = {}): Signal => ({
  id: 'sig-core-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  timestamp: now,
  type: 'BUY_WATCH',
  entryZone: [99, 101],
  stopLoss: 95,
  targets: [105, 110],
  validUntil: now + 10 * 60 * 1000,
  features: {
    confidence: 72.5,
    vwap: 98
  },
  status: 'ACTIVE',
  statusReason: 'Signal generated',
  latestPrice: 100,
  lastCheckedAt: now + 1_000,
  maxFavorableMovePercent: 1,
  maxAdverseMovePercent: 0.5,
  ...overrides
});

const makeCoreEvent = (overrides: Partial<SignalEvent> = {}): SignalEvent => ({
  id: 'event-core-1',
  signalId: 'sig-core-1',
  timestamp: now + 60_000,
  previousStatus: 'ACTIVE',
  newStatus: 'TARGET_HIT',
  reason: 'Target reached',
  latestPrice: 105,
  ...overrides
});

const makeCoreOutcome = (overrides: Partial<SignalOutcome> = {}): SignalOutcome => ({
  signalId: 'sig-core-1',
  finalStatus: 'TARGET_HIT',
  entryPrice: 100,
  exitPrice: 105,
  returnPercent: 5,
  maxFavorableMovePercent: 5,
  maxAdverseMovePercent: 1,
  openedAt: now,
  closedAt: now + 120_000,
  closeReason: 'Target reached',
  ...overrides
});

const makeCoreSnapshot = (overrides: Partial<MarketSnapshot> = {}): MarketSnapshot => ({
  ticker: 'SAMP.N0000',
  timestamp: now,
  lastPrice: 100,
  bestBid: 99.5,
  bestAsk: 100.5,
  bidDepth: 1_000,
  askDepth: 900,
  volume: 12_000,
  totalTurnover: 1_200_000,
  ...overrides
});

const makeCoreCandle = (overrides: Partial<Candle> = {}): Candle => ({
  ticker: 'SAMP.N0000',
  timestamp: now,
  open: 99,
  high: 102,
  low: 98,
  close: 101,
  volume: 10_000,
  vwap: 100,
  ...overrides
});

describe('core-to-db mapper functions', () => {
  it('maps core signal, event, outcome, snapshot, and candle fields', () => {
    const signal = makeCoreSignal();
    const event = makeCoreEvent();
    const outcome = makeCoreOutcome();
    const snapshot = makeCoreSnapshot();
    const candle = makeCoreCandle();

    expect(mapSignalToDbSignal(signal)).toMatchObject({
      id: signal.id,
      ticker: signal.ticker,
      strategy: signal.strategy,
      direction: 'BUY_WATCH',
      entryZoneLow: 99,
      entryZoneHigh: 101,
      confidence: 72.5
    });
    expect(mapSignalEventToDbSignalEvent(event)).toMatchObject({
      signalId: signal.id,
      previousStatus: 'ACTIVE',
      newStatus: 'TARGET_HIT',
      reason: 'Target reached'
    });
    expect(mapSignalOutcomeToDbSignalOutcome(outcome, signal)).toMatchObject({
      signalId: signal.id,
      ticker: signal.ticker,
      strategy: signal.strategy,
      finalStatus: 'TARGET_HIT'
    });
    expect(mapMarketSnapshotToDbMarketSnapshot(snapshot)).toMatchObject({
      ticker: signal.ticker,
      lastPrice: 100,
      bestBid: 99.5,
      bestAsk: 100.5,
      volume: 12_000
    });
    expect(mapCandleToDbCandle(candle)).toMatchObject({
      ticker: signal.ticker,
      timeframe: '5m',
      close: 101
    });
  });
});

describe('Supabase repository adapter boundary', () => {
  it('saving a signal maps fields correctly', async () => {
    const client = new FakeSupabaseClient();
    const repository = new SupabaseSignalRepository(client);
    const signal = makeCoreSignal();

    await repository.save(mapSignalToDbSignal(signal));

    expect(client.operations).toEqual([
      {
        table: 'signals',
        action: 'insert',
        values: expect.objectContaining({
          id: signal.id,
          ticker: signal.ticker,
          strategy: signal.strategy,
          direction: 'BUY_WATCH',
          entry_zone_low: 99,
          entry_zone_high: 101,
          stop_loss: 95,
          target1: 105,
          target2: 110,
          confidence: 72.5,
          latest_price: 100
        }),
        filters: []
      }
    ]);
  });

  it('updating a signal updates status, latest price, and status reason', async () => {
    const client = new FakeSupabaseClient();
    const repository = new SupabaseSignalRepository(client);

    await repository.update(
      mapSignalToDbSignal(
        makeCoreSignal({
          status: 'INVALIDATED',
          latestPrice: 97,
          statusReason: 'Price fell below VWAP'
        })
      )
    );

    expect(client.operations[0]).toMatchObject({
      table: 'signals',
      action: 'update',
      values: expect.objectContaining({
        status: 'INVALIDATED',
        latest_price: 97,
        status_reason: 'Price fell below VWAP'
      }),
      filters: [{ column: 'id', value: 'sig-core-1' }]
    });
  });

  it('recording a signal event stores signal_id, status transition, and reason', async () => {
    const client = new FakeSupabaseClient();
    const repository = new SupabaseSignalEventRepository(client);

    await repository.record(mapSignalEventToDbSignalEvent(makeCoreEvent()));

    expect(client.operations[0]).toMatchObject({
      table: 'signal_events',
      action: 'insert',
      values: expect.objectContaining({
        signal_id: 'sig-core-1',
        previous_status: 'ACTIVE',
        new_status: 'TARGET_HIT',
        reason: 'Target reached'
      })
    });
  });

  it('storing an outcome includes ticker and strategy directly', async () => {
    const client = new FakeSupabaseClient();
    const repository = new SupabaseSignalOutcomeRepository(client);
    const signal = makeCoreSignal();

    await repository.save(mapSignalOutcomeToDbSignalOutcome(makeCoreOutcome(), signal));

    expect(client.operations[0]).toMatchObject({
      table: 'signal_outcomes',
      action: 'insert',
      values: expect.objectContaining({
        signal_id: 'sig-core-1',
        ticker: 'SAMP.N0000',
        strategy: 'CSE_OPENING_MOMENTUM_V1',
        final_status: 'TARGET_HIT'
      })
    });
  });

  it('saving market snapshots maps ticker, price, bid/ask, and volume fields', async () => {
    const client = new FakeSupabaseClient();
    const repository = new SupabaseMarketSnapshotRepository(client);

    await repository.save(mapMarketSnapshotToDbMarketSnapshot(makeCoreSnapshot()));

    expect(client.operations[0]).toMatchObject({
      table: 'market_snapshots',
      action: 'insert',
      values: expect.objectContaining({
        ticker: 'SAMP.N0000',
        last_price: 100,
        best_bid: 99.5,
        best_ask: 100.5,
        volume: 12_000,
        total_turnover: 1_200_000
      })
    });
  });

  it('does not import or create a real Supabase client', () => {
    const source = readFileSync('packages/db/src/index.ts', 'utf8');

    expect(source).not.toContain('@supabase');
    expect(source).not.toContain('createClient');
    expect(source).not.toContain('process.env');
  });
});

interface FakeOperation {
  table: string;
  action: 'insert' | 'update' | 'select';
  values?: SupabaseRow | SupabaseRow[];
  filters: Array<{ column: string; value: unknown }>;
}

class FakeSupabaseClient implements SupabaseLikeClient {
  public readonly operations: FakeOperation[] = [];
  private readonly tables = new Map<string, SupabaseRow[]>();

  from<T = SupabaseRow>(tableName: string): SupabaseLikeTable<T> {
    return {
      insert: async (values) => {
        const rowsToInsert = (Array.isArray(values) ? values : [values]) as SupabaseRow[];
        const table = this.table(tableName);
        table.push(...rowsToInsert.map((row) => structuredClone(row)));
        this.operations.push({
          table: tableName,
          action: 'insert',
          values: Array.isArray(values) ? structuredClone(values as SupabaseRow[]) : structuredClone(values as SupabaseRow),
          filters: []
        });

        return {
          data: values,
          error: null
        } as SupabaseResult<T>;
      },
      update: (values) => new FakeSupabaseQuery<T>(this, tableName, 'update', values as SupabaseRow),
      select: () => new FakeSupabaseQuery<T>(this, tableName, 'select')
    };
  }

  execute(
    tableName: string,
    action: 'update' | 'select',
    filters: Array<{ column: string; value: unknown }>,
    values?: SupabaseRow
  ): SupabaseResult<SupabaseRow> {
    const table = this.table(tableName);

    if (action === 'update') {
      for (const row of table) {
        if (matchesFilters(row, filters)) {
          Object.assign(row, values);
        }
      }
    }

    const data = table.filter((row) => matchesFilters(row, filters)).map((row) => structuredClone(row));
    this.operations.push({
      table: tableName,
      action,
      values: values ? structuredClone(values) : undefined,
      filters: structuredClone(filters)
    });

    return {
      data,
      error: null
    };
  }

  private table(tableName: string): SupabaseRow[] {
    const existing = this.tables.get(tableName);
    if (existing) return existing;

    const created: SupabaseRow[] = [];
    this.tables.set(tableName, created);
    return created;
  }
}

class FakeSupabaseQuery<T = SupabaseRow> implements SupabaseLikeQuery<T> {
  private readonly filters: Array<{ column: string; value: unknown }> = [];

  constructor(
    private readonly client: FakeSupabaseClient,
    private readonly tableName: string,
    private readonly action: 'update' | 'select',
    private readonly values?: SupabaseRow
  ) {}

  eq(column: string, value: unknown): SupabaseLikeQuery<T> {
    this.filters.push({ column, value });
    return this;
  }

  async execute(): Promise<SupabaseResult<T>> {
    return this.client.execute(this.tableName, this.action, this.filters, this.values) as SupabaseResult<T>;
  }

  async maybeSingle(): Promise<SupabaseResult<T>> {
    const result = await this.execute();
    const data = Array.isArray(result.data) ? result.data[0] ?? null : result.data;

    return {
      data,
      error: result.error
    };
  }
}

function matchesFilters(row: SupabaseRow, filters: Array<{ column: string; value: unknown }>): boolean {
  return filters.every((filter) => row[filter.column] === filter.value);
}
