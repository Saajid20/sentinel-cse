import { Signal, SignalOutcome } from '@sentinel/core';
import { OpeningMomentumDetector } from '@sentinel/strategies';
import { MarketReplayEngine, ReplayResultSummary } from './replay.js';
import { BasketReplayScenario, averageVolumeByTickerForScenario } from './basketScenarios.js';
import { SentinelPipeline } from './pipeline.js';

export interface BasketScenarioResult {
  name: string;
  summary: ReplayResultSummary;
  signals: Signal[];
  outcomes: SignalOutcome[];
  scenarioReturnPercent: number;
}

export interface BasketReplayResult {
  scenarios: BasketScenarioResult[];
  totals: {
    scenariosProcessed: number;
    snapshotsProcessed: number;
    signalsGenerated: number;
    alertsSent: number;
    outcomesClosed: number;
  };
}

export interface StrategyPerformanceMetrics {
  totalScenarios: number;
  signalsGenerated: number;
  signalsBlocked: number;
  wins: number;
  losses: number;
  expired: number;
  invalidated: number;
  winRate: number;
  averageReturnPercent: number;
  averageMaxFavorableMovePercent: number;
  averageMaxAdverseMovePercent: number;
  profitFactor: number;
  bestScenario?: {
    name: string;
    returnPercent: number;
  };
  worstScenario?: {
    name: string;
    returnPercent: number;
  };
}

export interface LearningRecommendation {
  id: string;
  recommendation: string;
  reason: string;
  severity: 'low' | 'medium' | 'high';
  confidence: number;
  advisoryOnly: true;
}

export type PipelineFactory = (scenario: BasketReplayScenario) => SentinelPipeline;

export interface BasketReplayRunnerOptions {
  outcomeStrategyName?: string;
}

export class BasketReplayRunner {
  constructor(
    private readonly replayEngine: MarketReplayEngine = new MarketReplayEngine(),
    private readonly pipelineFactory: PipelineFactory = defaultPipelineFactory,
    private readonly options: BasketReplayRunnerOptions = {}
  ) {}

  async run(scenarios: BasketReplayScenario[]): Promise<BasketReplayResult> {
    const scenarioResults: BasketScenarioResult[] = [];
    const outcomeStrategyName = this.options.outcomeStrategyName ?? 'CSE_OPENING_MOMENTUM_V1';

    for (const scenario of scenarios) {
      const pipeline = this.pipelineFactory(scenario);
      const summary = await this.replayEngine.replay(scenario.snapshots, pipeline);
      const tickers = [...new Set(scenario.snapshots.map((snapshot) => snapshot.ticker))];
      const signals = (
        await Promise.all(tickers.map((ticker) => pipeline.memory.listSignalsByTicker(ticker)))
      ).flat();
      const outcomes = await pipeline.memory.getOutcomesByStrategy(outcomeStrategyName);

      scenarioResults.push({
        name: scenario.name,
        summary,
        signals,
        outcomes,
        scenarioReturnPercent: sum(outcomes.map((outcome) => outcome.returnPercent))
      });
    }

    return {
      scenarios: scenarioResults,
      totals: {
        scenariosProcessed: scenarioResults.length,
        snapshotsProcessed: sum(scenarioResults.map((result) => result.summary.snapshotsProcessed)),
        signalsGenerated: sum(scenarioResults.map((result) => result.summary.signalsGenerated)),
        alertsSent: sum(scenarioResults.map((result) => result.summary.alertsSent)),
        outcomesClosed: sum(scenarioResults.map((result) => result.summary.outcomesClosed))
      }
    };
  }
}

export class StrategyPerformanceEvaluator {
  evaluate(result: BasketReplayResult): StrategyPerformanceMetrics {
    const outcomes = result.scenarios.flatMap((scenario) => scenario.outcomes);
    const wins = outcomes.filter((outcome) => outcome.finalStatus === 'TARGET_HIT').length;
    const losses = outcomes.filter((outcome) => outcome.finalStatus === 'STOP_HIT').length;
    const expired = outcomes.filter((outcome) => outcome.finalStatus === 'EXPIRED').length;
    const invalidated = outcomes.filter((outcome) => outcome.finalStatus === 'INVALIDATED').length;
    const signalsBlocked = result.scenarios.filter((scenario) => scenario.summary.signalsGenerated === 0).length;
    const closedSignals = wins + losses + expired + invalidated;
    const grossPositiveReturns = sum(outcomes.map((outcome) => Math.max(0, outcome.returnPercent)));
    const grossNegativeReturns = Math.abs(sum(outcomes.map((outcome) => Math.min(0, outcome.returnPercent))));

    return {
      totalScenarios: result.scenarios.length,
      signalsGenerated: result.totals.signalsGenerated,
      signalsBlocked,
      wins,
      losses,
      expired,
      invalidated,
      winRate: closedSignals === 0 ? 0 : wins / closedSignals,
      averageReturnPercent: average(outcomes.map((outcome) => outcome.returnPercent)),
      averageMaxFavorableMovePercent: average(outcomes.map((outcome) => outcome.maxFavorableMovePercent)),
      averageMaxAdverseMovePercent: average(outcomes.map((outcome) => outcome.maxAdverseMovePercent)),
      profitFactor: grossNegativeReturns === 0 ? grossPositiveReturns : grossPositiveReturns / grossNegativeReturns,
      bestScenario: bestScenario(result.scenarios),
      worstScenario: worstScenario(result.scenarios)
    };
  }
}

export class LearningRecommendationEngine {
  recommend(result: BasketReplayResult, metrics: StrategyPerformanceMetrics): LearningRecommendation[] {
    if (metrics.totalScenarios < 5 || metrics.signalsGenerated < 3) {
      return [
        {
          id: 'keep-current-rules-small-sample',
          recommendation: 'Keep current rules until more mock replay samples are available.',
          reason: 'Sample size is too small for reliable parameter recommendations.',
          severity: 'low',
          confidence: 0.35,
          advisoryOnly: true
        }
      ];
    }

    const recommendations: LearningRecommendation[] = [];
    const outcomes = result.scenarios.flatMap((scenario) => scenario.outcomes);
    const spreadInvalidations = outcomes.filter(
      (outcome) => outcome.finalStatus === 'INVALIDATED' && /spread/i.test(outcome.closeReason)
    ).length;
    const lowVolumeUnderperformers = result.scenarios.flatMap((scenario) =>
      scenario.signals.filter((signal) => {
        const volumeRatio = signal.features['volumeRatio'];
        const outcome = scenario.outcomes.find((candidate) => candidate.signalId === signal.id);
        return typeof volumeRatio === 'number' && volumeRatio <= 2.5 && outcome !== undefined && outcome.returnPercent < 0;
      })
    ).length;

    if (spreadInvalidations >= 2 || (metrics.invalidated > 0 && spreadInvalidations / metrics.invalidated >= 0.5)) {
      recommendations.push({
        id: 'tighten-spread-threshold',
        recommendation: 'Review tightening the spread threshold for opening momentum entries.',
        reason: `${spreadInvalidations} invalidated signal(s) were caused by spread widening.`,
        severity: spreadInvalidations >= 3 ? 'high' : 'medium',
        confidence: Math.min(0.9, 0.45 + spreadInvalidations * 0.15),
        advisoryOnly: true
      });
    }

    if (lowVolumeUnderperformers >= 2) {
      recommendations.push({
        id: 'increase-volume-threshold',
        recommendation: 'Review increasing the volume ratio threshold for marginal opening momentum entries.',
        reason: `${lowVolumeUnderperformers} low-volume generated signal(s) underperformed after passing setup checks.`,
        severity: 'medium',
        confidence: Math.min(0.85, 0.4 + lowVolumeUnderperformers * 0.15),
        advisoryOnly: true
      });
    }

    if (metrics.expired >= 2 || (outcomes.length > 0 && metrics.expired / outcomes.length >= 0.3)) {
      recommendations.push({
        id: 'review-validity-window',
        recommendation: 'Review the entry validity window for opening momentum signals.',
        reason: `${metrics.expired} signal(s) expired without target, stop, or invalidation.`,
        severity: metrics.expired >= 3 ? 'high' : 'medium',
        confidence: Math.min(0.85, 0.45 + metrics.expired * 0.12),
        advisoryOnly: true
      });
    }

    const smallAdverseStopHits = outcomes.filter(
      (outcome) => outcome.finalStatus === 'STOP_HIT' && outcome.maxAdverseMovePercent <= 6
    ).length;
    if (smallAdverseStopHits >= 2) {
      recommendations.push({
        id: 'review-stop-loss',
        recommendation: 'Review stop-loss placement for signals stopped out after small adverse moves.',
        reason: `${smallAdverseStopHits} stop hit(s) occurred after relatively small adverse movement.`,
        severity: 'medium',
        confidence: Math.min(0.8, 0.4 + smallAdverseStopHits * 0.12),
        advisoryOnly: true
      });
    }

    if (recommendations.length === 0) {
      recommendations.push({
        id: 'keep-current-rules',
        recommendation: 'Keep current rules for now and continue collecting replay evidence.',
        reason: 'No failure mode dominated the current mock basket.',
        severity: 'low',
        confidence: 0.55,
        advisoryOnly: true
      });
    }

    return recommendations;
  }
}

function defaultPipelineFactory(scenario: BasketReplayScenario): SentinelPipeline {
  const detector = new OpeningMomentumDetector();
  detector.averageVolumeMap = averageVolumeByTickerForScenario(scenario);
  return new SentinelPipeline({ detector });
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function average(values: number[]): number {
  return values.length === 0 ? 0 : sum(values) / values.length;
}

function bestScenario(scenarios: BasketScenarioResult[]): StrategyPerformanceMetrics['bestScenario'] {
  if (scenarios.length === 0) return undefined;

  const best = [...scenarios].sort((left, right) => right.scenarioReturnPercent - left.scenarioReturnPercent)[0];
  return {
    name: best.name,
    returnPercent: best.scenarioReturnPercent
  };
}

function worstScenario(scenarios: BasketScenarioResult[]): StrategyPerformanceMetrics['worstScenario'] {
  if (scenarios.length === 0) return undefined;

  const worst = [...scenarios].sort((left, right) => left.scenarioReturnPercent - right.scenarioReturnPercent)[0];
  return {
    name: worst.name,
    returnPercent: worst.scenarioReturnPercent
  };
}
