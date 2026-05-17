import { pathToFileURL } from 'node:url';
import {
  defaultOpeningMomentumExperimentVariants,
  StrategyExperimentResult,
  StrategyExperimentRunner
} from '../apps/worker/src/index.js';
import {
  createManualATradLoginAndObserveConfig,
  runManualATradLoginAndObserve
} from './manualATradLoginAndObserve.js';
import { createManualATradLoginConfig, runManualATradLogin } from './manualATradLogin.js';
import { createManualATradObserveOnceConfig, runManualATradObserveOnce } from './manualATradObserveOnce.js';
import {
  createManualATradCompareSessionsConfig,
  runManualATradCompareSessions
} from './manualATradCompareSessions.js';
import {
  createManualATradReplaySessionConfig,
  runManualATradReplaySession
} from './manualATradReplaySession.js';
import {
  createManualATradRecordSessionConfig,
  runManualATradRecordSession
} from './manualATradRecordSession.js';
import {
  createValidateTradeableUniverseConfig,
  runValidateTradeableUniverse
} from './validateTradeableUniverse.js';
import { runManualBasketReplay } from './manualBasketReplay.js';
import { runManualSupabaseTest } from './manualSupabaseTest.js';
import { runManualTelegramTest } from './manualTelegramTest.js';

export type SentinelCommand =
  | 'status'
  | 'basket'
  | 'experiment'
  | 'atrad-login'
  | 'atrad-login-and-observe'
  | 'atrad-observe-once'
  | 'atrad-record-session'
  | 'atrad-replay-session'
  | 'atrad-compare-sessions'
  | 'universe-validate'
  | 'telegram-test'
  | 'supabase-test'
  | 'help';

export interface SentinelCommandResult {
  exitCode: number;
  output: string;
  error?: string;
}

export async function runSentinelCommand(args: string[]): Promise<SentinelCommandResult> {
  const command = args[0] ?? 'help';

  switch (command) {
    case 'status':
      return {
        exitCode: 0,
        output: formatStatus()
      };
    case 'basket':
      return {
        exitCode: 0,
        output: await formatBasketSummary()
      };
    case 'experiment':
      return {
        exitCode: 0,
        output: await formatExperimentSummary()
      };
    case 'atrad-login': {
      const config = createManualATradLoginConfig(args.slice(1));
      const sessionPath = await runManualATradLogin(config);
      return {
        exitCode: 0,
        output: config.persistentProfile
          ? `ATrad persistent profile ready at ${sessionPath}. Storage state also saved to ${config.storageStatePath}`
          : `ATrad manual login storage state saved to ${sessionPath}`
      };
    }
    case 'atrad-login-and-observe': {
      const result = await runManualATradLoginAndObserve(
        createManualATradLoginAndObserveConfig(args.slice(1))
      );
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.message
      };
    }
    case 'atrad-observe-once': {
      const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(args.slice(1)));
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.message
      };
    }
    case 'atrad-record-session': {
      const result = await runManualATradRecordSession(
        createManualATradRecordSessionConfig(args.slice(1))
      );
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.message
      };
    }
    case 'atrad-replay-session': {
      const result = await runManualATradReplaySession(
        createManualATradReplaySessionConfig(args.slice(1))
      );
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.message
      };
    }
    case 'atrad-compare-sessions': {
      const result = await runManualATradCompareSessions(
        createManualATradCompareSessionsConfig(args.slice(1))
      );
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.message
      };
    }
    case 'universe-validate': {
      const result = await runValidateTradeableUniverse(
        createValidateTradeableUniverseConfig(args.slice(1))
      );
      return {
        exitCode: result.ok ? 0 : 1,
        output: result.output
      };
    }
    case 'telegram-test':
      await runManualTelegramTest();
      return {
        exitCode: 0,
        output: 'Sent one manual Telegram test message.'
      };
    case 'supabase-test': {
      const snapshotId = await runManualSupabaseTest();
      return {
        exitCode: 0,
        output: `Supabase manual test succeeded: inserted and read market_snapshots row ${snapshotId}`
      };
    }
    case 'help':
      return {
        exitCode: 0,
        output: formatHelp()
      };
    default:
      return {
        exitCode: 1,
        output: formatHelp(),
        error: `Unknown Sentinel command: ${command}`
      };
  }
}

export function formatStatus(): string {
  return [
    'Sentinel-CSE v0.1 operator console',
    'Mode: signal-only paper-trading',
    '',
    'Implemented capabilities:',
    '- mock replay',
    '- basket evaluation',
    '- mock/real Telegram sender boundary',
    '- Supabase adapter/manual test',
    '- ATrad mock observer',
    '- tradeable universe validation',
    '',
    'Runtime mode:',
    '- default runtime mode: SHADOW',
    '- PAPER_ALERT mode available only when explicitly configured',
    '',
    'Safety status:',
    '- auto-trading disabled',
    '- order placement disabled',
    '- ATrad live connection disabled'
  ].join('\n');
}

export async function formatBasketSummary(): Promise<string> {
  const summary = await runManualBasketReplay();
  const { result, metrics, recommendations } = summary;

  return [
    'Sentinel-CSE mock basket replay summary',
    `Scenarios processed: ${result.totals.scenariosProcessed}`,
    `Snapshots processed: ${result.totals.snapshotsProcessed}`,
    `Signals generated: ${metrics.signalsGenerated}`,
    `Signals blocked: ${metrics.signalsBlocked}`,
    `Wins/Losses/Expired/Invalidated: ${metrics.wins}/${metrics.losses}/${metrics.expired}/${metrics.invalidated}`,
    `Win rate: ${formatPercent(metrics.winRate)}`,
    `Average return: ${formatSignedPercent(metrics.averageReturnPercent)}`,
    `Profit factor: ${formatNumber(metrics.profitFactor)}`,
    'Recommendations:',
    ...recommendations.map(
      (recommendation) =>
        `- ${recommendation.recommendation} (${recommendation.severity}, confidence ${formatPercent(
          recommendation.confidence
        )}) Reason: ${recommendation.reason}`
    )
  ].join('\n');
}

export async function formatExperimentSummary(): Promise<string> {
  const runner = new StrategyExperimentRunner();
  const results = await runner.run(defaultOpeningMomentumExperimentVariants);

  return [
    'Sentinel-CSE strategy experiment summary',
    'Mode: signal-only paper-trading',
    'Experiment set: Opening Momentum parameter variants',
    '',
    ...results.flatMap((result, index) => formatExperimentResult(result, index))
  ].join('\n');
}

export function formatHelp(): string {
  return [
    'Sentinel-CSE operator console',
    '',
    'Usage:',
    '  pnpm sentinel status',
    '  pnpm sentinel basket',
    '  pnpm sentinel experiment',
    '  pnpm sentinel atrad-login',
    '  pnpm sentinel atrad-login-and-observe',
    '  pnpm sentinel atrad-observe-once',
    '  pnpm sentinel atrad-record-session',
    '  pnpm sentinel atrad-replay-session',
    '  pnpm sentinel atrad-compare-sessions',
    '  pnpm sentinel universe-validate --config <path>',
    '  pnpm sentinel telegram-test',
    '  pnpm sentinel supabase-test',
    '  pnpm sentinel help',
    '',
    'Commands:',
    '  status         Show local capability and safety status.',
    '  basket         Run the mock basket replay evaluator.',
    '  experiment     Run Opening Momentum parameter experiments against the mock basket.',
    '  atrad-login    Open a local manual ATrad login browser and save ignored session state. Supports --persistent-profile.',
    '  atrad-login-and-observe  Log in manually, then observe the current same-session page without reopening the browser.',
    '  atrad-observe-once  Read Market Watch rows once using saved local storage state or --persistent-profile.',
    '  atrad-record-session  Record usable read-only Market Watch snapshots to an ignored local JSON session file.',
    '  atrad-replay-session  Replay a recorded local ATrad session JSON file through the safe local replay engine.',
    '  atrad-compare-sessions  Compare one or more recorded local ATrad session JSON files for replay readiness.',
    '  universe-validate  Validate a local tradeable universe JSON config.',
    '  telegram-test  Send exactly one manual Telegram test message using local environment variables.',
    '  supabase-test  Insert and read one harmless Supabase market_snapshots test row.',
    '  help           Show this help text.'
  ].join('\n');
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function formatSignedPercent(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : String(value);
}

function formatExperimentResult(result: StrategyExperimentResult, index: number): string[] {
  const recommendation = result.recommendations[0];
  const { metrics } = result;

  return [
    `${index + 1}. Variant: ${result.variant.name}`,
    `   Strategy: ${result.variant.parameters.strategyName}`,
    `   Signals generated: ${metrics.signalsGenerated}`,
    `   Signals blocked: ${metrics.signalsBlocked}`,
    `   Wins: ${metrics.wins}`,
    `   Losses: ${metrics.losses}`,
    `   Expired: ${metrics.expired}`,
    `   Invalidated: ${metrics.invalidated}`,
    `   Win rate: ${formatPercent(metrics.winRate)}`,
    `   Average return: ${formatSignedPercent(metrics.averageReturnPercent)}`,
    `   Profit factor: ${formatNumber(metrics.profitFactor)}`,
    `   Best scenario: ${formatScenario(metrics.bestScenario)}`,
    `   Worst scenario: ${formatScenario(metrics.worstScenario)}`,
    `   Top recommendation: ${formatRecommendation(recommendation)}`,
    ''
  ];
}

function formatScenario(
  scenario: { name: string; returnPercent: number } | undefined
): string {
  if (!scenario) return 'n/a';
  return `${scenario.name} (${formatSignedPercent(scenario.returnPercent)})`;
}

function formatRecommendation(
  recommendation:
    | {
        recommendation: string;
        severity: 'low' | 'medium' | 'high';
        confidence: number;
      }
    | undefined
): string {
  if (!recommendation) return 'n/a';

  return `${recommendation.recommendation} (${recommendation.severity}, confidence ${formatPercent(
    recommendation.confidence
  )})`;
}

async function main(): Promise<void> {
  const result = await runSentinelCommand(process.argv.slice(2));

  if (result.error) {
    console.error(result.error);
  }

  console.log(result.output);
  process.exitCode = result.exitCode;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Sentinel command failed: ${message}`);
    process.exitCode = 1;
  });
}
