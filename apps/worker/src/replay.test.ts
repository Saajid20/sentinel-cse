import { describe, expect, it } from 'vitest';
import { OpeningMomentumDetector } from '@sentinel/strategies';
import { MarketReplayEngine } from './replay.js';
import { replayScenarios } from './replayScenarios.js';
import { SentinelPipeline, SentinelRunMode } from './pipeline.js';

const ticker = 'SAMP.N0000';

const makePipeline = (mode?: SentinelRunMode): SentinelPipeline => {
  const detector = new OpeningMomentumDetector();
  detector.averageVolumeMap[ticker] = 100;

  return new SentinelPipeline({
    detector,
    runtime: mode ? { mode, orderPlacementEnabled: false } : undefined
  });
};

describe('MarketReplayEngine', () => {
  it('processes snapshots in timestamp order', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.multiTickerOutOfOrder(), pipeline, {
      tickerFilter: ticker
    });
    const savedSnapshots = await pipeline.db.marketSnapshots.listByTicker(ticker);

    expect(savedSnapshots.map((snapshot) => snapshot.snapshotTime)).toEqual([0, 60_000, 300_000, 301_000]);
    expect(summary.snapshotsProcessed).toBe(4);
    expect(summary.startTime).toBe(0);
    expect(summary.endTime).toBe(301_000);
  });

  it('generates a BUY WATCH alert for a qualifying scenario', async () => {
    const pipeline = makePipeline('PAPER_ALERT');
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumTargetHit(), pipeline);
    const messages = pipeline.sender.listSentMessages();

    expect(summary.signalsGenerated).toBe(1);
    expect(messages[0]).toMatchObject({
      kind: 'BUY_WATCH',
      ticker
    });
    expect(messages[0]?.text).toContain('BUY WATCH: SAMP.N0000');
  });

  it('closes an outcome when target is hit', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumTargetHit(), pipeline);
    const outcomes = await pipeline.db.signalOutcomes.listByStrategy('CSE_OPENING_MOMENTUM_V1');

    expect(summary.outcomesClosed).toBe(1);
    expect(outcomes).toMatchObject([
      {
        ticker,
        strategy: 'CSE_OPENING_MOMENTUM_V1',
        finalStatus: 'TARGET_HIT'
      }
    ]);
    expect(summary.finalActiveSignals).toEqual([]);
  });

  it('expires a signal when validity window passes', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumExpired(), pipeline);
    const outcomes = await pipeline.memory.getOutcomesByStrategy('CSE_OPENING_MOMENTUM_V1');

    expect(summary.outcomesClosed).toBe(1);
    expect(outcomes).toMatchObject([
      {
        finalStatus: 'EXPIRED',
        closeReason: 'Signal validity window elapsed'
      }
    ]);
  });

  it('invalidates a signal when spread widens', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumInvalidatedBySpread(), pipeline);
    const outcomes = await pipeline.memory.getOutcomesByStrategy('CSE_OPENING_MOMENTUM_V1');

    expect(summary.outcomesClosed).toBe(1);
    expect(outcomes).toMatchObject([
      {
        finalStatus: 'INVALIDATED',
        closeReason: 'Spread exceeded 2%'
      }
    ]);
  });

  it('does not generate a signal for a failed-risk scenario', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.failedRiskChecks(), pipeline);

    expect(summary.signalsGenerated).toBe(0);
    expect(summary.alertsSent).toBe(0);
    expect(summary.outcomesClosed).toBe(0);
    expect(summary.finalActiveSignals).toEqual([]);
  });

  it('returns correct replay summary counts', async () => {
    const pipeline = makePipeline('PAPER_ALERT');
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumTargetHit(), pipeline);

    expect(summary).toMatchObject({
      snapshotsProcessed: 5,
      signalsGenerated: 1,
      alertsSent: 2,
      outcomesClosed: 1,
      finalActiveSignals: [],
      startTime: 0,
      endTime: 361_000
    });
  });

  it('runs replay in SHADOW mode without alerts', async () => {
    const pipeline = makePipeline();
    const engine = new MarketReplayEngine();

    const summary = await engine.replay(replayScenarios.openingMomentumTargetHit(), pipeline);

    expect(summary.signalsGenerated).toBe(1);
    expect(summary.alertsSent).toBe(0);
    expect(pipeline.sender.listSentMessages()).toEqual([]);
  });
});
