import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import type { MarketSnapshot } from '@sentinel/core';
import {
  MarketReplayEngine,
  ReplayResultSummary,
  SentinelPipeline
} from '../apps/worker/src/index.js';
import type { ATradRecordedSession } from './manualATradRecordSession.js';

export interface ManualATradReplaySessionConfig {
  inputPath: string;
  readonlyMode: true;
}

export interface ATradReplayTickerCount {
  ticker: string;
  snapshotCount: number;
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
