import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DbSignal, DbSignalEvent, DbSignalOutcome, InMemoryDbAdapter } from './index.js';

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
