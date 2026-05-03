import {
  BasketReplayRunner,
  LearningRecommendationEngine,
  StrategyPerformanceEvaluator,
  basketReplayScenarios
} from '../apps/worker/src/index.js';

async function main(): Promise<void> {
  const runner = new BasketReplayRunner();
  const result = await runner.run(basketReplayScenarios);
  const evaluator = new StrategyPerformanceEvaluator();
  const metrics = evaluator.evaluate(result);
  const recommendations = new LearningRecommendationEngine().recommend(result, metrics);

  console.log('Sentinel-CSE mock basket replay summary');
  console.log(JSON.stringify({ totals: result.totals, metrics, recommendations }, null, 2));
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Mock basket replay failed: ${message}`);
  process.exitCode = 1;
});
