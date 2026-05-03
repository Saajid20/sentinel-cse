import { describe, expect, it } from 'vitest';
import { Signal, SignalOutcome } from '@sentinel/core';
import {
  BasketReplayResult,
  BasketReplayRunner,
  LearningRecommendationEngine,
  StrategyPerformanceEvaluator
} from './basket.js';
import { BasketReplayScenario, basketReplayScenarios } from './basketScenarios.js';
import { SentinelPipeline } from './pipeline.js';

describe('BasketReplayRunner', () => {
  it('processes all scenarios', async () => {
    const runner = new BasketReplayRunner();

    const result = await runner.run(basketReplayScenarios);

    expect(result.scenarios).toHaveLength(12);
    expect(result.totals.scenariosProcessed).toBe(12);
    expect(result.totals.snapshotsProcessed).toBeGreaterThan(0);
  });

  it('uses a fresh pipeline instance for each scenario', async () => {
    const pipelines: SentinelPipeline[] = [];
    const scenarios = basketReplayScenarios.slice(0, 3);
    const runner = new BasketReplayRunner(undefined, (_scenario: BasketReplayScenario) => {
      const pipeline = new SentinelPipeline();
      pipelines.push(pipeline);
      return pipeline;
    });

    await runner.run(scenarios);

    expect(pipelines).toHaveLength(3);
    expect(new Set(pipelines).size).toBe(3);
  });
});

describe('StrategyPerformanceEvaluator', () => {
  const evaluator = new StrategyPerformanceEvaluator();

  it('calculates win rate correctly', () => {
    const metrics = evaluator.evaluate(
      makeBasketResult([
        scenarioResult('winner', [outcome({ finalStatus: 'TARGET_HIT', returnPercent: 5 })], 1),
        scenarioResult('loser', [outcome({ finalStatus: 'STOP_HIT', returnPercent: -3 })], 1),
        scenarioResult('blocked', [], 0)
      ])
    );

    expect(metrics.winRate).toBe(0.5);
  });

  it('calculates average return correctly', () => {
    const metrics = evaluator.evaluate(
      makeBasketResult([
        scenarioResult('winner', [outcome({ returnPercent: 6 })], 1),
        scenarioResult('loser', [outcome({ finalStatus: 'STOP_HIT', returnPercent: -2 })], 1)
      ])
    );

    expect(metrics.averageReturnPercent).toBe(2);
  });

  it('separates blocked scenarios from generated signals', () => {
    const metrics = evaluator.evaluate(
      makeBasketResult([
        scenarioResult('generated', [outcome()], 1),
        scenarioResult('blocked-1', [], 0),
        scenarioResult('blocked-2', [], 0)
      ])
    );

    expect(metrics.signalsGenerated).toBe(1);
    expect(metrics.signalsBlocked).toBe(2);
  });

  it('calculates profit factor safely', () => {
    const noLossMetrics = evaluator.evaluate(
      makeBasketResult([
        scenarioResult('winner-1', [outcome({ returnPercent: 3 })], 1),
        scenarioResult('winner-2', [outcome({ returnPercent: 2 })], 1)
      ])
    );
    const mixedMetrics = evaluator.evaluate(
      makeBasketResult([
        scenarioResult('winner', [outcome({ returnPercent: 6 })], 1),
        scenarioResult('loser', [outcome({ finalStatus: 'STOP_HIT', returnPercent: -3 })], 1)
      ])
    );

    expect(noLossMetrics.profitFactor).toBe(5);
    expect(mixedMetrics.profitFactor).toBe(2);
  });
});

describe('LearningRecommendationEngine', () => {
  const evaluator = new StrategyPerformanceEvaluator();
  const recommender = new LearningRecommendationEngine();

  it('recommends tightening spread threshold when spread-related failures dominate', () => {
    const result = makeBasketResult([
      scenarioResult('spread-1', [outcome({ finalStatus: 'INVALIDATED', closeReason: 'Spread exceeded 2%' })], 1),
      scenarioResult('spread-2', [outcome({ finalStatus: 'INVALIDATED', closeReason: 'Spread exceeded 2%' })], 1),
      scenarioResult('winner', [outcome({ finalStatus: 'TARGET_HIT', returnPercent: 4 })], 1),
      scenarioResult('blocked-1', [], 0),
      scenarioResult('blocked-2', [], 0)
    ]);

    const recommendations = recommender.recommend(result, evaluator.evaluate(result));

    expect(recommendations).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'tighten-spread-threshold', advisoryOnly: true })])
    );
  });

  it('recommends increasing volume threshold when low-volume signals underperform', () => {
    const result = makeBasketResult([
      scenarioResult('low-volume-stop-1', [outcome({ signalId: 'sig-low-1', finalStatus: 'STOP_HIT', returnPercent: -3 })], 1, [
        signal({ id: 'sig-low-1', volumeRatio: 2.1 })
      ]),
      scenarioResult('low-volume-stop-2', [outcome({ signalId: 'sig-low-2', finalStatus: 'STOP_HIT', returnPercent: -2 })], 1, [
        signal({ id: 'sig-low-2', volumeRatio: 2.3 })
      ]),
      scenarioResult('winner', [outcome({ signalId: 'sig-win', returnPercent: 4 })], 1, [
        signal({ id: 'sig-win', volumeRatio: 3.5 })
      ]),
      scenarioResult('blocked-1', [], 0),
      scenarioResult('blocked-2', [], 0)
    ]);

    const recommendations = recommender.recommend(result, evaluator.evaluate(result));

    expect(recommendations).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'increase-volume-threshold', advisoryOnly: true })])
    );
  });

  it('recommends reviewing validity window when many signals expire', () => {
    const result = makeBasketResult([
      scenarioResult('expired-1', [outcome({ finalStatus: 'EXPIRED', closeReason: 'Signal validity window elapsed' })], 1),
      scenarioResult('expired-2', [outcome({ finalStatus: 'EXPIRED', closeReason: 'Signal validity window elapsed' })], 1),
      scenarioResult('winner', [outcome({ finalStatus: 'TARGET_HIT', returnPercent: 4 })], 1),
      scenarioResult('blocked-1', [], 0),
      scenarioResult('blocked-2', [], 0)
    ]);

    const recommendations = recommender.recommend(result, evaluator.evaluate(result));

    expect(recommendations).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'review-validity-window', advisoryOnly: true })])
    );
  });

  it('returns conservative no-change recommendation when sample size is too small', () => {
    const result = makeBasketResult([
      scenarioResult('winner', [outcome({ finalStatus: 'TARGET_HIT', returnPercent: 4 })], 1),
      scenarioResult('blocked', [], 0)
    ]);

    const recommendations = recommender.recommend(result, evaluator.evaluate(result));

    expect(recommendations).toEqual([
      expect.objectContaining({
        id: 'keep-current-rules-small-sample',
        advisoryOnly: true
      })
    ]);
  });
});

function makeBasketResult(scenarios: BasketReplayResult['scenarios']): BasketReplayResult {
  return {
    scenarios,
    totals: {
      scenariosProcessed: scenarios.length,
      snapshotsProcessed: scenarios.length,
      signalsGenerated: scenarios.reduce((total, scenario) => total + scenario.summary.signalsGenerated, 0),
      alertsSent: 0,
      outcomesClosed: scenarios.reduce((total, scenario) => total + scenario.outcomes.length, 0)
    }
  };
}

function scenarioResult(
  name: string,
  outcomes: SignalOutcome[],
  signalsGenerated: number,
  signals: Signal[] = outcomes.map((candidate) => signal({ id: candidate.signalId }))
): BasketReplayResult['scenarios'][number] {
  return {
    name,
    summary: {
      snapshotsProcessed: 1,
      signalsGenerated,
      alertsSent: signalsGenerated,
      outcomesClosed: outcomes.length,
      finalActiveSignals: []
    },
    signals,
    outcomes,
    scenarioReturnPercent: outcomes.reduce((total, candidate) => total + candidate.returnPercent, 0)
  };
}

function outcome(overrides: Partial<SignalOutcome> = {}): SignalOutcome {
  return {
    signalId: 'sig-1',
    finalStatus: 'TARGET_HIT',
    entryPrice: 100,
    exitPrice: 105,
    returnPercent: 5,
    maxFavorableMovePercent: 5,
    maxAdverseMovePercent: 1,
    openedAt: 1_000,
    closedAt: 2_000,
    closeReason: 'Target reached',
    ...overrides
  };
}

function signal({ id = 'sig-1', volumeRatio = 3 }: { id?: string; volumeRatio?: number } = {}): Signal {
  return {
    id,
    ticker: 'SAMP.N0000',
    strategy: 'CSE_OPENING_MOMENTUM_V1',
    timestamp: 1_000,
    type: 'BUY_WATCH',
    entryZone: [99, 101],
    stopLoss: 95,
    targets: [105, 110],
    validUntil: 10_000,
    features: { volumeRatio },
    status: 'ACTIVE'
  };
}
