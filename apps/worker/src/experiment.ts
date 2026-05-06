import { OpeningMomentumDetector, OpeningMomentumParameters } from '@sentinel/strategies';
import {
  BasketReplayResult,
  BasketReplayRunner,
  LearningRecommendation,
  LearningRecommendationEngine,
  StrategyPerformanceEvaluator,
  StrategyPerformanceMetrics
} from './basket.js';
import {
  BasketReplayScenario,
  averageVolumeByTickerForScenario,
  basketReplayScenarios
} from './basketScenarios.js';
import { SentinelPipeline } from './pipeline.js';

export interface StrategyExperimentVariant {
  name: string;
  description?: string;
  parameters: Partial<OpeningMomentumParameters> & Pick<OpeningMomentumParameters, 'strategyName'>;
}

export interface StrategyExperimentResult {
  variant: StrategyExperimentVariant;
  basketResult: BasketReplayResult;
  metrics: StrategyPerformanceMetrics;
  recommendations: LearningRecommendation[];
}

export const defaultOpeningMomentumExperimentVariants: StrategyExperimentVariant[] = [
  {
    name: 'baseline',
    description: 'Current Opening Momentum defaults with a variant-specific strategy name.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_BASELINE'
    }
  },
  {
    name: 'tighter-spread-threshold',
    description: 'Tighten the allowed entry spread.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_SPREAD_TIGHT',
      spreadPercentThreshold: 1
    }
  },
  {
    name: 'higher-volume-threshold',
    description: 'Require stronger opening volume confirmation.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_VOLUME_TIGHT',
      volumeRatioThreshold: 2.5
    }
  },
  {
    name: 'tighter-stop-loss',
    description: 'Use a tighter stop buffer under the setup structure.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_TIGHT_STOP',
      stopLossBufferPercent: 0.5
    }
  },
  {
    name: 'max-vwap-distance-filter',
    description: 'Reject entries that extend too far above VWAP.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_VWAP_DISTANCE',
      maxVwapDistancePercent: 8
    }
  },
  {
    name: 'strict-combo',
    description: 'Combine stricter spread, volume, imbalance, stop, and VWAP extension rules.',
    parameters: {
      strategyName: 'CSE_OPENING_MOMENTUM_V1_STRICT_COMBO',
      spreadPercentThreshold: 1,
      volumeRatioThreshold: 2.5,
      orderBookImbalanceThreshold: 0.2,
      stopLossBufferPercent: 0.5,
      maxVwapDistancePercent: 8,
      validityMinutes: 8
    }
  }
];

export class StrategyExperimentRunner {
  constructor(
    private readonly performanceEvaluator: StrategyPerformanceEvaluator = new StrategyPerformanceEvaluator(),
    private readonly recommendationEngine: LearningRecommendationEngine = new LearningRecommendationEngine()
  ) {}

  async run(
    variants: StrategyExperimentVariant[] = defaultOpeningMomentumExperimentVariants,
    scenarios: BasketReplayScenario[] = basketReplayScenarios
  ): Promise<StrategyExperimentResult[]> {
    const results: StrategyExperimentResult[] = [];

    for (const variant of variants) {
      const basketRunner = new BasketReplayRunner(
        undefined,
        (scenario) => this.createPipeline(variant, scenario),
        { outcomeStrategyName: variant.parameters.strategyName }
      );
      const basketResult = await basketRunner.run(scenarios);
      const metrics = this.performanceEvaluator.evaluate(basketResult);
      const recommendations = this.recommendationEngine.recommend(basketResult, metrics);

      results.push({
        variant,
        basketResult,
        metrics,
        recommendations
      });
    }

    return results;
  }

  private createPipeline(
    variant: StrategyExperimentVariant,
    scenario: BasketReplayScenario
  ): SentinelPipeline {
    const detector = new OpeningMomentumDetector(variant.parameters);
    detector.averageVolumeMap = averageVolumeByTickerForScenario(scenario);

    return new SentinelPipeline({ detector });
  }
}
