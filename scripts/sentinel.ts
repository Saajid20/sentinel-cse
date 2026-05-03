import { pathToFileURL } from 'node:url';
import { runManualBasketReplay } from './manualBasketReplay.js';
import { runManualSupabaseTest } from './manualSupabaseTest.js';
import { runManualTelegramTest } from './manualTelegramTest.js';

export type SentinelCommand = 'status' | 'basket' | 'telegram-test' | 'supabase-test' | 'help';

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

export function formatHelp(): string {
  return [
    'Sentinel-CSE operator console',
    '',
    'Usage:',
    '  pnpm sentinel status',
    '  pnpm sentinel basket',
    '  pnpm sentinel telegram-test',
    '  pnpm sentinel supabase-test',
    '  pnpm sentinel help',
    '',
    'Commands:',
    '  status         Show local capability and safety status.',
    '  basket         Run the mock basket replay evaluator.',
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
