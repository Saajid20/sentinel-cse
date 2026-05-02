import { describe, expect, it } from 'vitest';
import { Signal } from '@sentinel/core';
import { MockTelegramAlertSender, TelegramAlertFormatter } from './index.js';

const makeSignal = (overrides: Partial<Signal> = {}): Signal => ({
  id: 'sig-1',
  ticker: 'SAMP.N0000',
  strategy: 'CSE_OPENING_MOMENTUM_V1',
  timestamp: Date.UTC(2026, 0, 1, 4, 30),
  type: 'BUY_WATCH',
  entryZone: [99, 101],
  stopLoss: 95,
  targets: [105, 110],
  validUntil: Date.UTC(2026, 0, 1, 4, 40),
  features: {
    confidence: 72.5,
    reasons: ['price above VWAP', 'volume ratio above 2', 'bid depth stronger than ask depth']
  },
  status: 'ACTIVE',
  latestPrice: 100,
  lastCheckedAt: Date.UTC(2026, 0, 1, 4, 31),
  maxFavorableMovePercent: 1.5,
  maxAdverseMovePercent: 0.5,
  statusReason: 'Signal remains valid',
  ...overrides
});

describe('TelegramAlertFormatter', () => {
  const formatter = new TelegramAlertFormatter();

  it('formats a BUY WATCH alert', () => {
    const message = formatter.formatBuyWatch(makeSignal());

    expect(message.kind).toBe('BUY_WATCH');
    expect(message.signalId).toBe('sig-1');
    expect(message.text).toContain('BUY WATCH: SAMP.N0000');
    expect(message.text).toContain('Strategy: CSE_OPENING_MOMENTUM_V1');
    expect(message.text).toContain('Entry zone: 99.00 - 101.00');
    expect(message.text).toContain('Stop loss: 95.00');
    expect(message.text).toContain('Target 1: 105.00');
    expect(message.text).toContain('Target 2: 110.00');
    expect(message.text).toContain('Confidence: 72.50%');
    expect(message.text).toContain('Valid until: 2026-01-01T04:40:00.000Z');
    expect(message.text).toContain('Reasons: price above VWAP; volume ratio above 2; bid depth stronger than ask depth');
    expect(message.text).toContain('Invalidation rules: price below VWAP; spread above 2%; price leaves entry zone before entry');
    expect(message.text).toContain('Latest price: 100.00');
  });

  it('formats an EXPIRED update', () => {
    const message = formatter.formatExpiredUpdate(
      makeSignal({ status: 'EXPIRED', statusReason: 'Signal validity window elapsed' })
    );

    expect(message.kind).toBe('EXPIRED_UPDATE');
    expect(message.text).toContain('EXPIRED: SAMP.N0000');
    expect(message.text).toContain('Status reason: Signal validity window elapsed');
  });

  it('formats an INVALIDATED update', () => {
    const message = formatter.formatInvalidatedUpdate(
      makeSignal({ status: 'INVALIDATED', statusReason: 'Price fell below VWAP', latestPrice: 97 })
    );

    expect(message.kind).toBe('INVALIDATED_UPDATE');
    expect(message.text).toContain('INVALIDATED: SAMP.N0000');
    expect(message.text).toContain('Status reason: Price fell below VWAP');
    expect(message.text).toContain('Latest price: 97.00');
  });

  it('formats a TARGET_HIT update', () => {
    const message = formatter.formatTargetHitUpdate(
      makeSignal({ status: 'TARGET_HIT', statusReason: 'Target 105 reached', latestPrice: 105 })
    );

    expect(message.kind).toBe('TARGET_HIT_UPDATE');
    expect(message.text).toContain('TARGET HIT: SAMP.N0000');
    expect(message.text).toContain('Status reason: Target 105 reached');
  });

  it('formats a STOP_HIT update', () => {
    const message = formatter.formatStopHitUpdate(
      makeSignal({ status: 'STOP_HIT', statusReason: 'Stop loss reached', latestPrice: 95 })
    );

    expect(message.kind).toBe('STOP_HIT_UPDATE');
    expect(message.text).toContain('STOP HIT: SAMP.N0000');
    expect(message.text).toContain('Status reason: Stop loss reached');
  });
});

describe('MockTelegramAlertSender', () => {
  it('stores sent messages in memory', async () => {
    const formatter = new TelegramAlertFormatter();
    const sender = new MockTelegramAlertSender();
    const message = formatter.formatBuyWatch(makeSignal());

    await sender.send(message);

    expect(sender.listSentMessages()).toEqual([message]);

    sender.clear();
    expect(sender.listSentMessages()).toEqual([]);
  });
});
