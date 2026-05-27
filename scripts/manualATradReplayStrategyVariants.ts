import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { MarketReplayEngine, SentinelPipeline } from '../apps/worker/src/index.js';
import {
  DEFAULT_OPENING_MOMENTUM_PARAMETERS,
  OpeningMomentumDetector,
  type OpeningMomentumParameters
} from '../packages/strategies/src/index.js';
import {
  extractReplayableATradSnapshots,
  parseATradRecordedSessionFile
} from './manualATradReplaySession.js';

export interface ManualATradReplayStrategyVariantsConfig {
  inputPath: string;
  topSignalTickers: number;
  readonlyMode: true;
}

export interface ManualATradReplayStrategyVariantsRuntime {
  readFile(path: string): Promise<string>;
  log(message: string): void;
}

export interface StrategyVariantDefinition {
  name: string;
  diagnosticOnly: boolean;
  description: string;
  parameterOverrides: Partial<OpeningMomentumParameters>;
}

export interface StrategyVariantSignalTickerCount {
  ticker: string;
  count: number;
}

export interface StrategyVariantReplayResult {
  name: string;
  diagnosticOnly: boolean;
  description: string;
  parameterOverrides: Partial<OpeningMomentumParameters>;
  runtimeMode: 'SHADOW';
  replayedSnapshots: number;
  signalsGenerated: number;
  uniqueSignalTickers: number;
  signalTickerCounts: StrategyVariantSignalTickerCount[];
  generatedStrategies: string[];
}

export interface ManualATradReplayStrategyVariantsResult {
  ok: boolean;
  message: string;
  sessionId: string;
  source: string;
  startedAt: string;
  endedAt: string;
  totalSnapshotsLoaded: number;
  uniqueTickers: number;
  topSignalTickerLimit: number;
  variants: StrategyVariantReplayResult[];
}

export const FIXED_OPENING_MOMENTUM_VARIANTS: StrategyVariantDefinition[] = [
  {
    name: 'baseline',
    diagnosticOnly: false,
    description: 'Default Opening Momentum detector parameters.',
    parameterOverrides: {}
  },
  {
    name: 'volume-ratio-disabled-diagnostic',
    diagnosticOnly: true,
    description:
      'Diagnostic-only variant that neutralizes the volume-ratio gate with volumeRatioThreshold = -1.',
    parameterOverrides: {
      volumeRatioThreshold: -1
    }
  },
  {
    name: 'lower-volume-ratio-threshold',
    diagnosticOnly: true,
    description:
      'Diagnostic-only variant that lowers the volume-ratio threshold to 1.2 for offline comparison.',
    parameterOverrides: {
      volumeRatioThreshold: 1.2
    }
  }
];

export function createManualATradReplayStrategyVariantsConfig(
  args: string[] = []
): ManualATradReplayStrategyVariantsConfig {
  const inputPath = readFlagValue(args, '--input');
  if (!inputPath) {
    throw new Error('Missing required --input <path> for ATrad strategy variant replay.');
  }

  const parsedTop = readFlagValue(args, '--top');
  const topSignalTickers = parsedTop ? Number.parseInt(parsedTop, 10) : 10;

  return {
    inputPath,
    topSignalTickers: Number.isFinite(topSignalTickers) ? Math.max(topSignalTickers, 0) : 10,
    readonlyMode: true
  };
}

export async function runManualATradReplayStrategyVariants(
  config: ManualATradReplayStrategyVariantsConfig = createManualATradReplayStrategyVariantsConfig(),
  runtime: ManualATradReplayStrategyVariantsRuntime = defaultRuntime()
): Promise<ManualATradReplayStrategyVariantsResult> {
  if (config.readonlyMode !== true) {
    throw new Error('ATrad strategy variant replay must run in readonlyMode.');
  }

  const contents = await loadATradReplayInput(config.inputPath, runtime);
  const session = parseATradRecordedSessionFile(contents);
  const snapshots = extractReplayableATradSnapshots(session);
  const replayEngine = new MarketReplayEngine();
  const variants: StrategyVariantReplayResult[] = [];

  for (const variant of FIXED_OPENING_MOMENTUM_VARIANTS) {
    const detector = new OpeningMomentumDetector(variant.parameterOverrides);
    const pipeline = new SentinelPipeline({
      detector,
      runtime: { mode: 'SHADOW' }
    });
    const replaySummary = await replayEngine.replay(snapshots, pipeline);
    const tickerCounts = new Map<string, number>();
    const generatedStrategies = new Set<string>();

    for (const signal of replaySummary.generatedSignals) {
      tickerCounts.set(signal.ticker, (tickerCounts.get(signal.ticker) ?? 0) + 1);
      generatedStrategies.add(signal.strategy);
    }

    variants.push({
      name: variant.name,
      diagnosticOnly: variant.diagnosticOnly,
      description: variant.description,
      parameterOverrides: { ...variant.parameterOverrides },
      runtimeMode: 'SHADOW',
      replayedSnapshots: replaySummary.snapshotsProcessed,
      signalsGenerated: replaySummary.signalsGenerated,
      uniqueSignalTickers: tickerCounts.size,
      signalTickerCounts: [...tickerCounts.entries()]
        .map(([ticker, count]) => ({ ticker, count }))
        .sort((left, right) => right.count - left.count || left.ticker.localeCompare(right.ticker)),
      generatedStrategies: [...generatedStrategies].sort((left, right) => left.localeCompare(right))
    });
  }

  const result: ManualATradReplayStrategyVariantsResult = {
    ok: true,
    message: 'ATrad strategy variant replay completed.',
    sessionId: session.sessionId,
    source: session.source,
    startedAt: session.startedAt,
    endedAt: session.endedAt,
    totalSnapshotsLoaded: snapshots.length,
    uniqueTickers: new Set(snapshots.map((snapshot) => snapshot.ticker)).size,
    topSignalTickerLimit: config.topSignalTickers,
    variants
  };

  for (const line of formatATradReplayStrategyVariantsSummary(result)) {
    runtime.log(line);
  }

  return result;
}

export function formatATradReplayStrategyVariantsSummary(
  result: ManualATradReplayStrategyVariantsResult
): string[] {
  const lines = [
    'Sentinel-CSE ATrad strategy variant replay comparison',
    'warning: offline research only; SHADOW replay only; no production thresholds changed',
    `sessionId: ${result.sessionId}`,
    `source: ${result.source}`,
    `startedAt: ${result.startedAt}`,
    `endedAt: ${result.endedAt}`,
    `total snapshots loaded: ${result.totalSnapshotsLoaded}`,
    `unique tickers: ${result.uniqueTickers}`,
    `top signal tickers per variant: ${result.topSignalTickerLimit}`
  ];

  for (const variant of result.variants) {
    lines.push('');
    lines.push(`variant: ${variant.name}`);
    lines.push(`- diagnostic only: ${variant.diagnosticOnly ? 'yes' : 'no'}`);
    lines.push(`- runtime mode: ${variant.runtimeMode}`);
    lines.push(`- description: ${variant.description}`);
    lines.push(`- parameter overrides: ${formatParameterOverrides(variant.parameterOverrides)}`);
    lines.push(`- replayed snapshots: ${variant.replayedSnapshots}`);
    lines.push(`- signals generated: ${variant.signalsGenerated}`);
    lines.push(`- unique signal tickers: ${variant.uniqueSignalTickers}`);
    lines.push(`- generated strategies: ${formatStringList(variant.generatedStrategies)}`);
    lines.push(`- top signal tickers: ${formatSignalTickerCounts(variant.signalTickerCounts, result.topSignalTickerLimit)}`);
  }

  return lines;
}

async function loadATradReplayInput(
  path: string,
  runtime: ManualATradReplayStrategyVariantsRuntime
): Promise<string> {
  try {
    return await runtime.readFile(path);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Unable to read recorded ATrad session file: ${path}. ${message}`);
  }
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function formatParameterOverrides(overrides: Partial<OpeningMomentumParameters>): string {
  const entries = Object.entries(overrides).sort(([left], [right]) => left.localeCompare(right));
  if (entries.length === 0) {
    return 'default';
  }

  return entries.map(([key, value]) => `${key}=${formatParameterValue(value)}`).join(', ');
}

function formatParameterValue(value: unknown): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(value);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return String(value);
}

function formatStringList(values: string[]): string {
  if (values.length === 0) {
    return 'none';
  }
  return values.join(', ');
}

function formatSignalTickerCounts(
  counts: StrategyVariantSignalTickerCount[],
  topLimit: number
): string {
  if (counts.length === 0 || topLimit === 0) {
    return 'none';
  }

  return counts
    .slice(0, topLimit)
    .map((item) => `${item.ticker}:${item.count}`)
    .join(', ');
}

function defaultRuntime(): ManualATradReplayStrategyVariantsRuntime {
  return {
    readFile: async (path) => readFile(path, 'utf8'),
    log: (message) => console.log(message)
  };
}

async function main(): Promise<void> {
  const result = await runManualATradReplayStrategyVariants(
    createManualATradReplayStrategyVariantsConfig(process.argv.slice(2))
  );
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  void main();
}

export const BASELINE_OPENING_MOMENTUM_PARAMETERS = { ...DEFAULT_OPENING_MOMENTUM_PARAMETERS };
