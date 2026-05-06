import { describe, expect, it } from 'vitest';
import { MarketDataSanitizer, MarketSnapshot } from '@sentinel/core';
import { OpeningMomentumDetector } from '@sentinel/strategies';
import { SentinelPipeline } from './pipeline.js';

const ticker = 'SAMP.N0000';

const snapshot = (overrides: Partial<MarketSnapshot>): MarketSnapshot => ({
  ticker,
  timestamp: 0,
  lastPrice: 50,
  bestBid: 49.5,
  bestAsk: 50,
  bidDepth: 1_000,
  askDepth: 800,
  volume: 100,
  totalTurnover: 5_000,
  ...overrides
});

const makePipeline = (): SentinelPipeline => {
  const detector = new OpeningMomentumDetector();
  detector.averageVolumeMap[ticker] = 100;

  return new SentinelPipeline({ detector });
};

const buildFirstCandle = async (pipeline: SentinelPipeline): Promise<void> => {
  await pipeline.processSnapshot(snapshot({ timestamp: 0, lastPrice: 50, volume: 100 }));
  await pipeline.processSnapshot(snapshot({ timestamp: 60_000, lastPrice: 52, volume: 50 }));
  await pipeline.processSnapshot(snapshot({ timestamp: 300_000, lastPrice: 52, volume: 0 }));
};

const qualifyingSnapshot = (timestamp = 301_000): MarketSnapshot =>
  snapshot({
    timestamp,
    lastPrice: 55,
    bestBid: 54.5,
    bestAsk: 55,
    bidDepth: 2_000,
    askDepth: 1_000,
    volume: 300,
    totalTurnover: 16_500
  });

const createSignal = async (pipeline: SentinelPipeline) => {
  await buildFirstCandle(pipeline);
  const result = await pipeline.processSnapshot(qualifyingSnapshot());
  if (!result.generatedSignal) throw new Error('Expected pipeline to generate a signal');

  return result.generatedSignal;
};

describe('SentinelPipeline', () => {
  it('creates a signal from qualifying mock snapshots', async () => {
    const pipeline = makePipeline();

    const signal = await createSignal(pipeline);

    expect(signal.ticker).toBe(ticker);
    expect(signal.strategy).toBe('CSE_OPENING_MOMENTUM_V1');
    expect(signal.status).toBe('ACTIVE');
    expect(signal.type).toBe('BUY_WATCH');
  });

  it('sends a mock BUY WATCH alert', async () => {
    const pipeline = makePipeline();

    const signal = await createSignal(pipeline);
    const messages = pipeline.sender.listSentMessages();

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      kind: 'BUY_WATCH',
      signalId: signal.id,
      ticker
    });
    expect(messages[0]?.text).toContain('BUY WATCH: SAMP.N0000');
  });

  it('stores generated signals in memory and db', async () => {
    const pipeline = makePipeline();

    const signal = await createSignal(pipeline);

    await expect(pipeline.memory.getSignal(signal.id)).resolves.toEqual(signal);
    await expect(pipeline.db.signals.getById(signal.id)).resolves.toMatchObject({
      id: signal.id,
      ticker,
      strategy: 'CSE_OPENING_MOMENTUM_V1',
      status: 'ACTIVE'
    });
  });

  it('records an event when a signal expires', async () => {
    const pipeline = makePipeline();
    const signal = await createSignal(pipeline);

    const result = await pipeline.processSnapshot(
      snapshot({
        timestamp: signal.validUntil + 1,
        lastPrice: 55,
        bestBid: 54.5,
        bestAsk: 55,
        volume: 50
      })
    );

    expect(result.events).toHaveLength(1);
    expect(result.events[0]).toMatchObject({
      signalId: signal.id,
      previousStatus: 'ACTIVE',
      newStatus: 'EXPIRED',
      reason: 'Signal validity window elapsed'
    });
    await expect(pipeline.memory.listEventsBySignal(signal.id)).resolves.toHaveLength(1);
    await expect(pipeline.db.signalEvents.listBySignal(signal.id)).resolves.toHaveLength(1);
  });

  it('sends a lifecycle update when target is hit', async () => {
    const pipeline = makePipeline();
    const signal = await createSignal(pipeline);

    await pipeline.processSnapshot(
      snapshot({
        timestamp: signal.timestamp + 60_000,
        lastPrice: 58,
        bestBid: 57.5,
        bestAsk: 58,
        volume: 50
      })
    );

    const messages = pipeline.sender.listSentMessages();
    expect(messages).toHaveLength(2);
    expect(messages[1]).toMatchObject({
      kind: 'TARGET_HIT_UPDATE',
      signalId: signal.id
    });
    expect(messages[1]?.text).toContain('TARGET HIT: SAMP.N0000');
  });

  it('closes an outcome on final status', async () => {
    const pipeline = makePipeline();
    const signal = await createSignal(pipeline);

    await pipeline.processSnapshot(
      snapshot({
        timestamp: signal.timestamp + 60_000,
        lastPrice: 58,
        bestBid: 57.5,
        bestAsk: 58,
        volume: 50
      })
    );

    await expect(pipeline.memory.getOutcomesByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toMatchObject([
      {
        signalId: signal.id,
        finalStatus: 'TARGET_HIT',
        closeReason: 'Target 57.75 reached'
      }
    ]);
    await expect(pipeline.db.signalOutcomes.listByStrategy('CSE_OPENING_MOMENTUM_V1')).resolves.toMatchObject([
      {
        signalId: signal.id,
        ticker,
        strategy: 'CSE_OPENING_MOMENTUM_V1',
        finalStatus: 'TARGET_HIT'
      }
    ]);
  });

  it('does not create a signal when risk checks fail', async () => {
    const pipeline = makePipeline();
    await buildFirstCandle(pipeline);

    const result = await pipeline.processSnapshot(
      snapshot({
        timestamp: 301_000,
        lastPrice: 55,
        bestBid: 53,
        bestAsk: 55,
        bidDepth: 2_000,
        askDepth: 1_000,
        volume: 300,
        totalTurnover: 16_500
      })
    );

    expect(result.generatedSignal).toBeUndefined();
    expect(pipeline.sender.listSentMessages()).toEqual([]);
    await expect(pipeline.memory.listActiveSignals()).resolves.toEqual([]);
  });

  it('continues accepting MarketSnapshot input without automatic sanitizer wiring', async () => {
    const sanitizer = new MarketDataSanitizer();
    const pipeline = makePipeline();
    const sanitize = (raw: Record<string, string | number>) => {
      const result = sanitizer.sanitize(raw);
      if (!result.accepted || !result.snapshot) {
        throw new Error(`Expected accepted snapshot, got ${result.issues.map((issue) => issue.code).join(', ')}`);
      }

      return result.snapshot;
    };

    await pipeline.processSnapshot(
      sanitize({
        ticker,
        timestamp: '0',
        lastPrice: '50',
        bestBid: '49.5',
        bestAsk: '50',
        bidDepth: '1000',
        askDepth: '800',
        volume: '100'
      })
    );
    await pipeline.processSnapshot(
      sanitize({
        ticker,
        timestamp: '60000',
        lastPrice: '52',
        bestBid: '51.5',
        bestAsk: '52',
        bidDepth: '1000',
        askDepth: '800',
        volume: '50'
      })
    );
    await pipeline.processSnapshot(
      sanitize({
        ticker,
        timestamp: '300000',
        lastPrice: '52',
        bestBid: '51.5',
        bestAsk: '52',
        bidDepth: '1000',
        askDepth: '800',
        volume: '0'
      })
    );

    const result = await pipeline.processSnapshot(
      sanitize({
        ticker,
        timestamp: '301000',
        lastPrice: '55',
        bestBid: '54.5',
        bestAsk: '55',
        bidDepth: '2000',
        askDepth: '1000',
        volume: '300'
      })
    );

    expect(result.generatedSignal).toBeDefined();
    expect(result.generatedSignal?.strategy).toBe('CSE_OPENING_MOMENTUM_V1');
  });
});
