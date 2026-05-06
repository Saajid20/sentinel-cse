import { describe, expect, it } from 'vitest';
import { basketReplayScenarios } from './basketScenarios.js';
import {
  defaultOpeningMomentumExperimentVariants,
  StrategyExperimentRunner,
  StrategyExperimentVariant
} from './experiment.js';

describe('StrategyExperimentRunner', () => {
  it('processes multiple variants and returns one result per variant', async () => {
    const runner = new StrategyExperimentRunner();
    const variants = defaultOpeningMomentumExperimentVariants.slice(0, 3);

    const results = await runner.run(variants, basketReplayScenarios.slice(0, 4));

    expect(results).toHaveLength(variants.length);
    expect(results.map((result) => result.variant.name)).toEqual(variants.map((variant) => variant.name));
  });

  it('keeps pipeline and memory state isolated across variants and scenarios', async () => {
    const runner = new StrategyExperimentRunner();
    const variants: StrategyExperimentVariant[] = [
      {
        name: 'variant-a',
        parameters: {
          strategyName: 'CSE_OPENING_MOMENTUM_V1_VARIANT_A'
        }
      },
      {
        name: 'variant-b',
        parameters: {
          strategyName: 'CSE_OPENING_MOMENTUM_V1_VARIANT_B'
        }
      }
    ];

    const results = await runner.run(variants, basketReplayScenarios.slice(0, 2));

    expect(results).toHaveLength(2);

    for (const result of results) {
      expect(result.basketResult.scenarios).toHaveLength(2);
      expect(result.basketResult.totals.signalsGenerated).toBe(2);

      for (const scenario of result.basketResult.scenarios) {
        expect(scenario.signals).toHaveLength(1);
        expect(scenario.outcomes).toHaveLength(1);
        expect(scenario.signals[0]?.strategy).toBe(result.variant.parameters.strategyName);
        expect(scenario.outcomes[0]?.signalId).toContain(result.variant.parameters.strategyName);
      }
    }
  });

  it('gives each variant its own strategy name, metrics, and advisory recommendations', async () => {
    const runner = new StrategyExperimentRunner();

    const results = await runner.run(defaultOpeningMomentumExperimentVariants, basketReplayScenarios);

    expect(results).toHaveLength(defaultOpeningMomentumExperimentVariants.length);

    for (const result of results) {
      const generatedSignals = result.basketResult.scenarios.flatMap((scenario) => scenario.signals);

      expect(generatedSignals.length).toBeGreaterThan(0);
      expect(new Set(generatedSignals.map((signal) => signal.strategy))).toEqual(
        new Set([result.variant.parameters.strategyName])
      );
      expect(result.metrics).toMatchObject({
        totalScenarios: basketReplayScenarios.length
      });
      expect(result.metrics.signalsGenerated).toBeGreaterThan(0);
      expect(result.recommendations.length).toBeGreaterThan(0);
      expect(result.recommendations.every((recommendation) => recommendation.advisoryOnly)).toBe(true);
    }
  });

  it('runs the baseline and strict combo default variants successfully', async () => {
    const runner = new StrategyExperimentRunner();
    const variants = defaultOpeningMomentumExperimentVariants.filter((variant) =>
      ['baseline', 'strict-combo'].includes(variant.name)
    );

    const results = await runner.run(variants, basketReplayScenarios);

    expect(results).toHaveLength(2);
    expect(results).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          variant: expect.objectContaining({
            name: 'baseline',
            parameters: expect.objectContaining({
              strategyName: 'CSE_OPENING_MOMENTUM_V1_BASELINE'
            })
          }),
          metrics: expect.objectContaining({
            signalsGenerated: expect.any(Number)
          })
        }),
        expect.objectContaining({
          variant: expect.objectContaining({
            name: 'strict-combo',
            parameters: expect.objectContaining({
              strategyName: 'CSE_OPENING_MOMENTUM_V1_STRICT_COMBO'
            })
          }),
          metrics: expect.objectContaining({
            signalsGenerated: expect.any(Number)
          })
        })
      ])
    );

    expect(results.every((result) => result.metrics.signalsGenerated > 0)).toBe(true);
  });
});
