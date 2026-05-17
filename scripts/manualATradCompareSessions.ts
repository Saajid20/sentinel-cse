import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import {
  MarketReplayEngine,
  SentinelPipeline
} from '../apps/worker/src/index.js';
import {
  analyzeATradReplayDiagnostics,
  extractReplayableATradSnapshots,
  parseATradRecordedSessionFile,
  topTickersBySnapshotCount,
  type ATradReplayDiagnostics,
  type ATradReplayReadinessStatus,
  type ATradReplayTickerCount
} from './manualATradReplaySession.js';
import type { ATradRecordedSession } from './manualATradRecordSession.js';
import {
  filterSnapshotsByTradeableUniverse,
  parseTradeableUniverseConfig,
  type TradeableUniverseConfig,
  type TradeableUniverseCoverageSummary
} from './tradeableUniverse.js';

export interface ManualATradCompareSessionsConfig {
  inputPaths: string[];
  universePath?: string;
  readonlyMode: true;
}

export interface ATradSessionComparisonEntry {
  inputPath: string;
  sessionId: string;
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  totalSnapshotsLoaded: number;
  uniqueTickers: number;
  replayedSnapshots: number;
  enrichedSnapshots: number;
  snapshotsWithVwapEstimate: number;
  snapshotsWithFirstFiveMinuteHighEstimate: number;
  snapshotsWithVolumeRatioEstimate: number;
  snapshotsWithOrderBookImbalance: number;
  strategyReadySnapshots: number;
  readinessStatus: ATradReplayReadinessStatus;
  signalsGenerated: number;
  outcomesClosed: number;
  topBlocker: string;
  topTickers: ATradReplayTickerCount[];
  diagnostics: ATradReplayDiagnostics;
  universeCoverage?: TradeableUniverseCoverageSummary;
}

export interface ManualATradCompareSessionsResult {
  ok: boolean;
  message: string;
  sessions: ATradSessionComparisonEntry[];
  recommendations: string[];
  universeName?: string;
}

export interface ManualATradCompareSessionsRuntime {
  readFile(path: string): Promise<string>;
  log(message: string): void;
}

export function createManualATradCompareSessionsConfig(
  args: string[] = []
): ManualATradCompareSessionsConfig {
  const repeatedInputs = collectRepeatedFlagValues(args, '--input');
  const groupedInputs = (readFlagValues(args, '--inputs') ?? [])
    .flatMap((value) => value.split(','))
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  const inputPaths = [...repeatedInputs, ...groupedInputs];

  if (inputPaths.length === 0) {
    throw new Error('Missing required --input <path> or --inputs <path1,path2,...> for ATrad session comparison.');
  }

  return {
    inputPaths,
    ...(readFlagValue(args, '--universe') ? { universePath: readFlagValue(args, '--universe') } : {}),
    readonlyMode: true
  };
}

export async function runManualATradCompareSessions(
  config: ManualATradCompareSessionsConfig = createManualATradCompareSessionsConfig(),
  runtime: ManualATradCompareSessionsRuntime = defaultRuntime()
): Promise<ManualATradCompareSessionsResult> {
  if (config.readonlyMode !== true) {
    throw new Error('ATrad session comparison must run in readonlyMode.');
  }

  const universe = config.universePath
    ? parseTradeableUniverseConfig(
        await loadATradSessionFile(config.universePath, runtime),
        config.universePath
      )
    : undefined;
  const sessions: ATradSessionComparisonEntry[] = [];

  for (const inputPath of config.inputPaths) {
    const contents = await loadATradSessionFile(inputPath, runtime);
    const session = parseATradRecordedSessionFile(contents);
    const entry = await compareSingleRecordedSession(inputPath, session, universe);
    sessions.push(entry);
  }

  const recommendations = buildSessionComparisonRecommendations(sessions);
  const result: ManualATradCompareSessionsResult = {
    ok: true,
    message: 'ATrad recorded session comparison completed.',
    sessions,
    recommendations,
    ...(universe ? { universeName: universe.name } : {})
  };

  for (const line of formatATradSessionComparisonSummary(result)) {
    runtime.log(line);
  }

  return result;
}

export function buildSessionComparisonRecommendations(
  sessions: ATradSessionComparisonEntry[]
): string[] {
  const recommendations = new Set<string>();
  if (sessions.length === 0) {
    recommendations.add('capture at least one recorded session before comparing readiness.');
    return [...recommendations];
  }

  const bestDuration = [...sessions].sort(
    (left, right) => right.strategyReadySnapshots - left.strategyReadySnapshots
  )[0];

  if (sessions.some((session) => session.readinessStatus === 'NOT_READY')) {
    recommendations.add('record longer session');
  }

  if (sessions.some((session) => session.snapshotsWithVolumeRatioEstimate < session.totalSnapshotsLoaded / 2)) {
    recommendations.add('reduce interval seconds');
  }

  if (sessions.some((session) => session.diagnostics.tickersWithRepeatedSnapshots < session.uniqueTickers / 2)) {
    recommendations.add('focus on tickers with repeated observations');
  }

  if (sessions.some((session) => session.uniqueTickers > 50 && session.strategyReadySnapshots < 25)) {
    recommendations.add('create tradeable universe/custom watchlist');
  }

  if (sessions.some((session) => session.snapshotsWithFirstFiveMinuteHighEstimate < session.totalSnapshotsLoaded / 2)) {
    recommendations.add('improve strategy feature builder');
  }

  if (bestDuration && bestDuration.strategyReadySnapshots > 0) {
    recommendations.add('run replay experiment variants');
  }

  return [...recommendations];
}

export function formatATradSessionComparisonSummary(
  result: ManualATradCompareSessionsResult
): string[] {
  const lines = [
    'Sentinel-CSE ATrad recorded session comparison',
    `Sessions compared: ${result.sessions.length}`,
    ...(result.universeName ? [`Tradeable universe: ${result.universeName}`] : []),
    ''
  ];

  result.sessions.forEach((session, index) => {
    lines.push(`${index + 1}. ${session.sessionId}`);
    lines.push(`   input: ${session.inputPath}`);
    lines.push(`   startedAt: ${session.startedAt}`);
    lines.push(`   endedAt: ${session.endedAt}`);
    lines.push(`   duration seconds: ${session.durationSeconds}`);
    lines.push(`   total snapshots loaded: ${session.totalSnapshotsLoaded}`);
    if (session.universeCoverage) {
      lines.push(`   universe-filtered snapshots: ${session.universeCoverage.filteredSnapshots}`);
      lines.push(`   excluded by universe: ${session.universeCoverage.excludedByUniverse}`);
    }
    lines.push(`   unique tickers: ${session.uniqueTickers}`);
    lines.push(`   replayed snapshots: ${session.replayedSnapshots}`);
    lines.push(`   enriched snapshots: ${session.enrichedSnapshots}`);
    lines.push(`   snapshots with vwap/vwapEstimate: ${session.snapshotsWithVwapEstimate}`);
    lines.push(`   snapshots with first5MinHigh/sessionHigh estimate: ${session.snapshotsWithFirstFiveMinuteHighEstimate}`);
    lines.push(`   snapshots with volumeRatioEstimate: ${session.snapshotsWithVolumeRatioEstimate}`);
    lines.push(`   snapshots with orderBookImbalance: ${session.snapshotsWithOrderBookImbalance}`);
    lines.push(`   strategy-ready snapshots: ${session.strategyReadySnapshots}`);
    lines.push(`   readiness status: ${session.readinessStatus}`);
    lines.push(`   signals generated: ${session.signalsGenerated}`);
    lines.push(`   outcomes closed: ${session.outcomesClosed}`);
    lines.push(`   top blocker: ${session.topBlocker}`);
    lines.push('   top 5 tickers by snapshot count:');
    if (session.topTickers.length === 0) {
      lines.push('   - none');
    } else {
      session.topTickers.forEach((ticker) => {
        lines.push(`   - ${ticker.ticker}: ${ticker.snapshotCount}`);
      });
    }
    lines.push('');
  });

  lines.push('Aggregate recommendations:');
  result.recommendations.forEach((recommendation) => {
    lines.push(`- ${recommendation}`);
  });

  return lines;
}

async function compareSingleRecordedSession(
  inputPath: string,
  session: ATradRecordedSession,
  universe?: TradeableUniverseConfig
): Promise<ATradSessionComparisonEntry> {
  const loadedSnapshots = extractReplayableATradSnapshots(session);
  const universeResult = universe
    ? filterSnapshotsByTradeableUniverse(loadedSnapshots, universe)
    : undefined;
  const snapshots = universeResult?.snapshots ?? loadedSnapshots;
  const pipeline = new SentinelPipeline({ runtime: { mode: 'SHADOW' } });
  const replaySummary = await new MarketReplayEngine().replay(snapshots, pipeline);
  const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, replaySummary);

  return {
    inputPath,
    sessionId: session.sessionId,
    startedAt: session.startedAt,
    endedAt: session.endedAt,
    durationSeconds: calculateDurationSeconds(session.startedAt, session.endedAt),
    totalSnapshotsLoaded: loadedSnapshots.length,
    uniqueTickers: new Set(snapshots.map((snapshot) => snapshot.ticker)).size,
    replayedSnapshots: replaySummary.snapshotsProcessed,
    enrichedSnapshots: diagnostics.enrichedSnapshotsCount,
    snapshotsWithVwapEstimate: diagnostics.snapshotsWithVwapEstimate,
    snapshotsWithFirstFiveMinuteHighEstimate: diagnostics.snapshotsWithFirstFiveMinuteHighEstimate,
    snapshotsWithVolumeRatioEstimate: diagnostics.snapshotsWithVolumeRatioEstimate,
    snapshotsWithOrderBookImbalance: diagnostics.snapshotsWithOrderBookImbalance,
    strategyReadySnapshots: diagnostics.strategyReadySnapshotCount,
    readinessStatus: diagnostics.readinessStatus,
    signalsGenerated: replaySummary.signalsGenerated,
    outcomesClosed: replaySummary.outcomesClosed,
    topBlocker: diagnostics.likelyBlockers[0] ?? 'none',
    topTickers: topTickersBySnapshotCount(snapshots, 5),
    diagnostics,
    ...(universeResult ? { universeCoverage: universeResult.coverage } : {})
  };
}

async function loadATradSessionFile(
  path: string,
  runtime: ManualATradCompareSessionsRuntime
): Promise<string> {
  try {
    return await runtime.readFile(path);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Unable to read recorded ATrad session file: ${path}. ${message}`);
  }
}

function calculateDurationSeconds(startedAt: string, endedAt: string): number {
  const start = Date.parse(startedAt);
  const end = Date.parse(endedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return 0;
  }
  return Math.round((end - start) / 1000);
}

function collectRepeatedFlagValues(args: string[], flag: string): string[] {
  const values: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === flag) {
      const value = args[index + 1]?.trim();
      if (value) {
        values.push(value);
      }
    }
  }
  return values;
}

function readFlagValues(args: string[], flag: string): string[] | undefined {
  const values = collectRepeatedFlagValues(args, flag);
  return values.length > 0 ? values : undefined;
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function defaultRuntime(): ManualATradCompareSessionsRuntime {
  return {
    readFile: async (path) => readFile(path, 'utf8'),
    log: (message) => console.log(message)
  };
}

async function main(): Promise<void> {
  const result = await runManualATradCompareSessions(
    createManualATradCompareSessionsConfig(process.argv.slice(2))
  );
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad compare-sessions failed: ${message}`);
    process.exitCode = 1;
  });
}
