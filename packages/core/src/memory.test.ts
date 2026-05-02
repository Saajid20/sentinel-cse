import { describe, expect, it } from 'vitest';
import { InMemorySignalMemory } from './memory.js';
import { Signal, SignalEvent, SignalOutcome } from './types.js';

const makeSignal = (overrides: Partial<Signal> = {}): Signal => ({
  id: 'sig-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  timestamp: 1_000,
  type: 'BUY_WATCH',
  entryZone: [99, 101],
  stopLoss: 95,
  targets: [105, 110],
  validUntil: 601_000,
  features: {
    vwap: 98
  },
  status: 'ACTIVE',
  ...overrides
});

const makeOutcome = (overrides: Partial<SignalOutcome> = {}): SignalOutcome => ({
  signalId: 'sig-1',
  finalStatus: 'TARGET_HIT',
  entryPrice: 100,
  exitPrice: 105,
  returnPercent: 5,
  maxFavorableMovePercent: 5,
  maxAdverseMovePercent: 1,
  openedAt: 1_000,
  closedAt: 120_000,
  closeReason: 'Target 105 reached',
  ...overrides
});

describe('InMemorySignalMemory', () => {
  it('saves and retrieves a signal', async () => {
    const memory = new InMemorySignalMemory();
    const signal = makeSignal();

    await memory.saveSignal(signal);

    await expect(memory.getSignal('sig-1')).resolves.toEqual(signal);
    await expect(memory.getSignal('missing')).resolves.toBeNull();
  });

  it('records status transition events', async () => {
    const memory = new InMemorySignalMemory();
    const event: SignalEvent = {
      id: 'event-1',
      signalId: 'sig-1',
      timestamp: 120_000,
      previousStatus: 'ACTIVE',
      newStatus: 'INVALIDATED',
      reason: 'Price fell below VWAP',
      latestPrice: 97
    };

    await memory.recordEvent(event);

    await expect(memory.listEventsBySignal('sig-1')).resolves.toEqual([event]);
    await expect(memory.listEventsBySignal('missing')).resolves.toEqual([]);
  });

  it('lists active signals', async () => {
    const memory = new InMemorySignalMemory();
    const activeSignal = makeSignal({ id: 'active' });
    const expiredSignal = makeSignal({ id: 'expired', status: 'EXPIRED' });

    await memory.saveSignal(activeSignal);
    await memory.saveSignal(expiredSignal);

    await expect(memory.listActiveSignals()).resolves.toEqual([activeSignal]);
  });

  it('closes and retrieves an outcome by strategy', async () => {
    const memory = new InMemorySignalMemory();
    const signal = makeSignal();
    const outcome = makeOutcome();

    await memory.saveSignal(signal);
    await memory.closeSignalOutcome(outcome);

    await expect(memory.getOutcomesByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toEqual([outcome]);
  });

  it('lists outcomes by strategy', async () => {
    const memory = new InMemorySignalMemory();
    const openingSignal = makeSignal({ id: 'opening', strategy: 'CSE_OPENING_MOMENTUM_V1' });
    const otherSignal = makeSignal({ id: 'other', strategy: 'OTHER_STRATEGY' });
    const openingOutcome = makeOutcome({ signalId: 'opening' });
    const otherOutcome = makeOutcome({ signalId: 'other', finalStatus: 'STOP_HIT', closeReason: 'Stop loss reached' });

    await memory.saveSignal(openingSignal);
    await memory.saveSignal(otherSignal);
    await memory.closeSignalOutcome(openingOutcome);
    await memory.closeSignalOutcome(otherOutcome);

    await expect(memory.getOutcomesByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toEqual([openingOutcome]);
    await expect(memory.getOutcomesByStrategy('OTHER_STRATEGY')).resolves.toEqual([otherOutcome]);
  });
});
