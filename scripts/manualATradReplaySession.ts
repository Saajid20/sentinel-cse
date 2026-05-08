import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import type { MarketSnapshot } from '@sentinel/core';
import {
  MarketReplayEngine,
  ReplayResultSummary,
  SentinelPipeline
} from '../apps/worker/src/index.js';
import type { ATradRecordedSession } from './manualATradRecordSession.js';

const OPENING_MOMENTUM_SPREAD_THRESHOLD = 1.5;
const OPENING_MOMENTUM_IMBALANCE_THRESHOLD = 0;

export interface ManualATradReplaySessionConfig {
  inputPath: string;
  readonlyMode: true;
}

export interface ATradReplayTickerCount {
  ticker: string;
  snapshotCount: number;
}

export type ATradReplayReadinessStatus =
  | 'NOT_READY'
  | 'PARTIALLY_READY'
  | 'READY_FOR_SHADOW_REPLAY';

export interface ATradReplayTickerDiagnostic {
  ticker: string;
  snapshots: number;
  averageSpreadPercent?: number;
  latestLastPrice: number;
  latestBid: number;
  latestAsk: number;
  enoughObservations: boolean;
  strategyReady: boolean;
}

export interface ATradReplayDiagnostics {
  snapshotsProcessed: number;
  uniqueTickers: number;
  tickersWithRepeatedSnapshots: number;
  spreadBlockedCount: number;
  volumeBlockedCount: number;
  imbalanceBlockedCount: number;
  vwapMissingCount: number;
  firstFiveMinuteHighMissingCount: number;
  insufficientHistoryCount: number;
  qualityGateExcludedCount: number;
  strategyGeneratedSignalCount: number;
  strategyReadySnapshotCount: number;
  likelyBlockers: string[];
  recommendations: string[];
  readinessStatus: ATradReplayReadinessStatus;
  perTickerDiagnostics: ATradReplayTickerDiagnostic[];
}

export interface ManualATradReplaySessionResult {
  ok: boolean;
  message: string;
  sessionId: string;
  source: string;
  startedAt: string;
  endedAt: string;
  totalSnapshotsLoaded: number;
  uniqueTickers: number;
  topTickers: ATradReplayTickerCount[];
  replaySummary: ReplayResultSummary;
  diagnostics: ATradReplayDiagnostics;
  warning?: string;
}

export interface ManualATradReplaySessionRuntime {
  readFile(path: string): Promise<string>;
  log(message: string): void;
}

export function createManualATradReplaySessionConfig(
  args: string[] = []
): ManualATradReplaySessionConfig {
  const inputPath = readFlagValue(args, '--input');
  if (!inputPath) {
    throw new Error('Missing required --input <path> for ATrad session replay.');
  }

  return {
    inputPath,
    readonlyMode: true
  };
}

export function parseATradRecordedSessionFile(contents: string): ATradRecordedSession {
  let parsed: unknown;
  try {
    parsed = JSON.parse(contents);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Malformed ATrad session JSON: ${message}`);
  }

  if (!isRecordObject(parsed)) {
    throw new Error('Malformed ATrad session JSON: root object is invalid.');
  }

  if (typeof parsed.sessionId !== 'string' || parsed.sessionId.trim().length === 0) {
    throw new Error('Malformed ATrad session JSON: sessionId is required.');
  }

  if (typeof parsed.source !== 'string' || parsed.source.trim().length === 0) {
    throw new Error('Malformed ATrad session JSON: source is required.');
  }

  if (typeof parsed.startedAt !== 'string' || typeof parsed.endedAt !== 'string') {
    throw new Error('Malformed ATrad session JSON: startedAt and endedAt are required.');
  }

  if (!Array.isArray(parsed.snapshots)) {
    throw new Error('Malformed ATrad session JSON: snapshots must be an array.');
  }

  return parsed as ATradRecordedSession;
}

export function extractReplayableATradSnapshots(session: ATradRecordedSession): MarketSnapshot[] {
  return session.snapshots
    .filter(isReplayableSnapshot)
    .sort((left, right) => left.timestamp - right.timestamp)
    .map((snapshot) => ({
      ticker: snapshot.ticker,
      timestamp: snapshot.timestamp,
      lastPrice: snapshot.lastPrice,
      bestBid: snapshot.bestBid,
      bestAsk: snapshot.bestAsk,
      bidDepth: snapshot.bidDepth,
      askDepth: snapshot.askDepth,
      volume: snapshot.volume,
      totalTurnover: snapshot.totalTurnover
    }));
}

export function topTickersBySnapshotCount(
  snapshots: MarketSnapshot[],
  limit = 5
): ATradReplayTickerCount[] {
  const counts = new Map<string, number>();
  for (const snapshot of snapshots) {
    counts.set(snapshot.ticker, (counts.get(snapshot.ticker) ?? 0) + 1);
  }

  return [...counts.entries()]
    .map(([ticker, snapshotCount]) => ({ ticker, snapshotCount }))
    .sort((left, right) => right.snapshotCount - left.snapshotCount || left.ticker.localeCompare(right.ticker))
    .slice(0, limit);
}

export function analyzeATradReplayDiagnostics(
  session: ATradRecordedSession,
  snapshots: MarketSnapshot[],
  replaySummary: ReplayResultSummary
): ATradReplayDiagnostics {
  const grouped = groupSnapshotsByTicker(snapshots);
  const perTickerDiagnostics = [...grouped.entries()]
    .map(([ticker, entries]) => buildTickerDiagnostic(ticker, entries))
    .sort((left, right) => right.snapshots - left.snapshots || left.ticker.localeCompare(right.ticker))
    .slice(0, 10);

  const spreadBlockedCount = snapshots.filter((snapshot) => {
    const spreadPercent = calculateSpreadPercent(snapshot);
    return spreadPercent !== undefined && spreadPercent >= OPENING_MOMENTUM_SPREAD_THRESHOLD;
  }).length;

  const imbalanceBlockedCount = snapshots.filter(
    (snapshot) => calculateOrderBookImbalance(snapshot) <= OPENING_MOMENTUM_IMBALANCE_THRESHOLD
  ).length;

  const tickerCounts = new Map<string, number>(
    [...grouped.entries()].map(([ticker, entries]) => [ticker, entries.length])
  );
  const repeatedTickerSet = new Set(
    [...tickerCounts.entries()].filter(([, count]) => count >= 2).map(([ticker]) => ticker)
  );
  const insufficientHistoryCount = snapshots.filter(
    (snapshot) => (tickerCounts.get(snapshot.ticker) ?? 0) < 2
  ).length;
  const strategyReadySnapshotCount = snapshots.filter((snapshot) => {
    const spreadPercent = calculateSpreadPercent(snapshot);
    return (
      (tickerCounts.get(snapshot.ticker) ?? 0) >= 2 &&
      spreadPercent !== undefined &&
      spreadPercent < OPENING_MOMENTUM_SPREAD_THRESHOLD &&
      calculateOrderBookImbalance(snapshot) > OPENING_MOMENTUM_IMBALANCE_THRESHOLD
    );
  }).length;

  const qualityGateExcludedCount =
    (session.totals?.quarantinedSnapshots ?? 0) + (session.totals?.rejectedSnapshots ?? 0);
  const vwapMissingCount = snapshots.length;
  const firstFiveMinuteHighMissingCount = snapshots.length;
  const volumeBlockedCount = snapshots.length;

  const likelyBlockers = buildLikelyBlockers({
    insufficientHistoryCount,
    vwapMissingCount,
    volumeBlockedCount,
    firstFiveMinuteHighMissingCount,
    spreadBlockedCount,
    imbalanceBlockedCount
  });
  const readinessStatus = classifyReplayReadiness({
    repeatedTickerCount: repeatedTickerSet.size,
    snapshotsProcessed: snapshots.length,
    strategyReadySnapshotCount,
    vwapMissingCount,
    firstFiveMinuteHighMissingCount
  });

  return {
    snapshotsProcessed: replaySummary.snapshotsProcessed,
    uniqueTickers: grouped.size,
    tickersWithRepeatedSnapshots: repeatedTickerSet.size,
    spreadBlockedCount,
    volumeBlockedCount,
    imbalanceBlockedCount,
    vwapMissingCount,
    firstFiveMinuteHighMissingCount,
    insufficientHistoryCount,
    qualityGateExcludedCount,
    strategyGeneratedSignalCount: replaySummary.signalsGenerated,
    strategyReadySnapshotCount,
    likelyBlockers,
    recommendations: buildReplayRecommendations(readinessStatus),
    readinessStatus,
    perTickerDiagnostics
  };
}

export function formatATradReplaySessionSummary(
  result: ManualATradReplaySessionResult
): string[] {
  const lines = [
    'Sentinel-CSE ATrad recorded session replay summary',
    `sessionId: ${result.sessionId}`,
    `source: ${result.source}`,
    `startedAt: ${result.startedAt}`,
    `endedAt: ${result.endedAt}`,
    `total snapshots loaded: ${result.totalSnapshotsLoaded}`,
    `unique tickers: ${result.uniqueTickers}`,
    `replayed snapshots: ${result.replaySummary.snapshotsProcessed}`,
    `signals generated: ${result.replaySummary.signalsGenerated}`,
    `outcomes closed: ${result.replaySummary.outcomesClosed}`,
    'top tickers by snapshot count:'
  ];

  if (result.topTickers.length === 0) {
    lines.push('- none');
  } else {
    result.topTickers.forEach((entry) => {
      lines.push(`- ${entry.ticker}: ${entry.snapshotCount}`);
    });
  }

  if (result.warning) {
    lines.push(`warning: ${result.warning}`);
  }

  lines.push('', 'ATrad replay diagnostics:');
  lines.push(`- snapshots processed: ${result.diagnostics.snapshotsProcessed}`);
  lines.push(`- unique tickers: ${result.diagnostics.uniqueTickers}`);
  lines.push(`- tickers with repeated snapshots: ${result.diagnostics.tickersWithRepeatedSnapshots}`);
  result.diagnostics.likelyBlockers.forEach((blocker) => {
    lines.push(`- likely blocker: ${blocker}`);
  });
  lines.push(`- spread blocked: ${result.diagnostics.spreadBlockedCount}`);
  lines.push(`- volume blocked: ${result.diagnostics.volumeBlockedCount}`);
  lines.push(`- imbalance blocked: ${result.diagnostics.imbalanceBlockedCount}`);
  lines.push(`- VWAP missing or unusable: ${result.diagnostics.vwapMissingCount}`);
  lines.push(`- first-5-minute high missing or unusable: ${result.diagnostics.firstFiveMinuteHighMissingCount}`);
  lines.push(`- insufficient time-series history: ${result.diagnostics.insufficientHistoryCount}`);
  lines.push(`- sanitizer/quality gate excluded rows: ${result.diagnostics.qualityGateExcludedCount}`);
  lines.push(`- strategy-ready snapshots: ${result.diagnostics.strategyReadySnapshotCount}`);
  lines.push(`- readiness status: ${result.diagnostics.readinessStatus}`);
  result.diagnostics.recommendations.forEach((recommendation) => {
    lines.push(`- recommendation: ${recommendation}`);
  });
  lines.push('per-ticker diagnostics:');
  if (result.diagnostics.perTickerDiagnostics.length === 0) {
    lines.push('- none');
  } else {
    result.diagnostics.perTickerDiagnostics.forEach((ticker) => {
      lines.push(
        `- ${ticker.ticker}: snapshots=${ticker.snapshots}, avgSpread=${formatOptionalPercent(
          ticker.averageSpreadPercent
        )}, latestLast=${ticker.latestLastPrice.toFixed(2)}, latestBidAsk=${ticker.latestBid.toFixed(
          2
        )}/${ticker.latestAsk.toFixed(2)}, enoughObservations=${ticker.enoughObservations ? 'yes' : 'no'}, strategyReady=${ticker.strategyReady ? 'yes' : 'no'}`
      );
    });
  }

  return lines;
}

export async function runManualATradReplaySession(
  config: ManualATradReplaySessionConfig = createManualATradReplaySessionConfig(),
  runtime: ManualATradReplaySessionRuntime = defaultRuntime()
): Promise<ManualATradReplaySessionResult> {
  if (config.readonlyMode !== true) {
    throw new Error('ATrad session replay must run in readonlyMode.');
  }

  const contents = await loadATradReplayInput(config.inputPath, runtime);
  const session = parseATradRecordedSessionFile(contents);
  const snapshots = extractReplayableATradSnapshots(session);
  const pipeline = new SentinelPipeline({ runtime: { mode: 'SHADOW' } });
  const replayEngine = new MarketReplayEngine();
  const replaySummary = await replayEngine.replay(snapshots, pipeline);
  const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, replaySummary);
  const warning = replaySummary.signalsGenerated === 0
    ? 'No signals were generated during replay.'
    : undefined;

  const result: ManualATradReplaySessionResult = {
    ok: true,
    message: 'ATrad recorded session replay completed.',
    sessionId: session.sessionId,
    source: session.source,
    startedAt: session.startedAt,
    endedAt: session.endedAt,
    totalSnapshotsLoaded: snapshots.length,
    uniqueTickers: new Set(snapshots.map((snapshot) => snapshot.ticker)).size,
    topTickers: topTickersBySnapshotCount(snapshots),
    replaySummary,
    diagnostics,
    warning
  };

  for (const line of formatATradReplaySessionSummary(result)) {
    runtime.log(line);
  }

  return result;
}

async function loadATradReplayInput(
  path: string,
  runtime: ManualATradReplaySessionRuntime
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

function isRecordObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isReplayableSnapshot(value: unknown): value is MarketSnapshot {
  if (!isRecordObject(value)) {
    return false;
  }

  return (
    typeof value.ticker === 'string' &&
    typeof value.timestamp === 'number' &&
    typeof value.lastPrice === 'number' &&
    typeof value.bestBid === 'number' &&
    typeof value.bestAsk === 'number' &&
    typeof value.bidDepth === 'number' &&
    typeof value.askDepth === 'number' &&
    typeof value.volume === 'number' &&
    typeof value.totalTurnover === 'number'
  );
}

function groupSnapshotsByTicker(snapshots: MarketSnapshot[]): Map<string, MarketSnapshot[]> {
  const grouped = new Map<string, MarketSnapshot[]>();
  for (const snapshot of snapshots) {
    const existing = grouped.get(snapshot.ticker);
    if (existing) {
      existing.push(snapshot);
    } else {
      grouped.set(snapshot.ticker, [snapshot]);
    }
  }
  return grouped;
}

function buildTickerDiagnostic(
  ticker: string,
  snapshots: MarketSnapshot[]
): ATradReplayTickerDiagnostic {
  const latest = snapshots[snapshots.length - 1] ?? snapshots[0];
  const spreadValues = snapshots
    .map(calculateSpreadPercent)
    .filter((value): value is number => value !== undefined);
  const averageSpreadPercent = spreadValues.length > 0
    ? spreadValues.reduce((total, value) => total + value, 0) / spreadValues.length
    : undefined;
  const enoughObservations = snapshots.length >= 2;
  const strategyReady =
    enoughObservations &&
    averageSpreadPercent !== undefined &&
    averageSpreadPercent < OPENING_MOMENTUM_SPREAD_THRESHOLD &&
    calculateOrderBookImbalance(latest) > OPENING_MOMENTUM_IMBALANCE_THRESHOLD;

  return {
    ticker,
    snapshots: snapshots.length,
    averageSpreadPercent,
    latestLastPrice: latest.lastPrice,
    latestBid: latest.bestBid,
    latestAsk: latest.bestAsk,
    enoughObservations,
    strategyReady
  };
}

function calculateSpreadPercent(snapshot: MarketSnapshot): number | undefined {
  if (snapshot.bestAsk <= 0) {
    return undefined;
  }
  return ((snapshot.bestAsk - snapshot.bestBid) / snapshot.bestAsk) * 100;
}

function calculateOrderBookImbalance(snapshot: MarketSnapshot): number {
  const denominator = snapshot.bidDepth + snapshot.askDepth;
  if (denominator === 0) {
    return 0;
  }
  return (snapshot.bidDepth - snapshot.askDepth) / denominator;
}

function buildLikelyBlockers(counts: {
  insufficientHistoryCount: number;
  vwapMissingCount: number;
  volumeBlockedCount: number;
  firstFiveMinuteHighMissingCount: number;
  spreadBlockedCount: number;
  imbalanceBlockedCount: number;
}): string[] {
  const blockers: string[] = [];
  if (counts.insufficientHistoryCount > 0) {
    blockers.push('insufficient time-series history');
  }
  if (counts.volumeBlockedCount > 0) {
    blockers.push('volume ratio unavailable');
  }
  if (counts.vwapMissingCount > 0) {
    blockers.push('VWAP missing');
  }
  if (counts.firstFiveMinuteHighMissingCount > 0) {
    blockers.push('first-5-minute high missing');
  }
  if (counts.spreadBlockedCount > 0) {
    blockers.push('spread too wide');
  }
  if (counts.imbalanceBlockedCount > 0) {
    blockers.push('order book imbalance below threshold');
  }
  return blockers.slice(0, 4);
}

function classifyReplayReadiness(input: {
  repeatedTickerCount: number;
  snapshotsProcessed: number;
  strategyReadySnapshotCount: number;
  vwapMissingCount: number;
  firstFiveMinuteHighMissingCount: number;
}): ATradReplayReadinessStatus {
  if (input.repeatedTickerCount === 0 || input.snapshotsProcessed === 0) {
    return 'NOT_READY';
  }

  if (
    input.strategyReadySnapshotCount === 0 ||
    input.vwapMissingCount > 0 ||
    input.firstFiveMinuteHighMissingCount > 0
  ) {
    return 'PARTIALLY_READY';
  }

  return 'READY_FOR_SHADOW_REPLAY';
}

function buildReplayRecommendations(status: ATradReplayReadinessStatus): string[] {
  if (status === 'NOT_READY') {
    return [
      'record longer session with interval <= 10s',
      'capture more repeated ticker observations before replay'
    ];
  }

  if (status === 'PARTIALLY_READY') {
    return [
      'record longer session with interval <= 10s',
      'add feature builder for real ATrad snapshots'
    ];
  }

  return ['continue collecting longer real sessions and compare replay outputs'];
}

function formatOptionalPercent(value: number | undefined): string {
  return value === undefined ? 'n/a' : `${value.toFixed(2)}%`;
}

function defaultRuntime(): ManualATradReplaySessionRuntime {
  return {
    readFile: async (path) => readFile(path, 'utf8'),
    log: (message) => console.log(message)
  };
}

async function main(): Promise<void> {
  const result = await runManualATradReplaySession(
    createManualATradReplaySessionConfig(process.argv.slice(2))
  );
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad replay-session failed: ${message}`);
    process.exitCode = 1;
  });
}
