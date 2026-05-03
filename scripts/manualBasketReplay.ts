import {
  BasketReplayResult,
  BasketReplayRunner,
  LearningRecommendationEngine,
  LearningRecommendation,
  StrategyPerformanceMetrics,
  StrategyPerformanceEvaluator,
  basketReplayScenarios
} from '../apps/worker/src/index.js';
import { pathToFileURL } from 'node:url';

export interface ManualBasketReplaySummary {
  result: BasketReplayResult;
  metrics: StrategyPerformanceMetrics;
  recommendations: LearningRecommendation[];
}

export async function runManualBasketReplay(): Promise<ManualBasketReplaySummary> {
  const runner = new BasketReplayRunner();
  const result = await runner.run(basketReplayScenarios);
  const evaluator = new StrategyPerformanceEvaluator();
  const metrics = evaluator.evaluate(result);
  const recommendations = new LearningRecommendationEngine().recommend(result, metrics);

  return {
    result,
    metrics,
    recommendations
  };
}

export function formatManualBasketReplaySummary(summary: ManualBasketReplaySummary): string {
  return JSON.stringify(
    {
      totals: summary.result.totals,
      metrics: summary.metrics,
      recommendations: summary.recommendations
    },
    null,
    2
  );
}

async function main(): Promise<void> {
  const summary = await runManualBasketReplay();

  console.log('Sentinel-CSE mock basket replay summary');
  console.log(formatManualBasketReplaySummary(summary));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Mock basket replay failed: ${message}`);
    process.exitCode = 1;
  });
}
