import { readdir, readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import {
  extractReplayableATradSnapshots,
  parseATradRecordedSessionFile
} from './manualATradReplaySession.js';
import type { ATradRecordedSession } from './manualATradRecordSession.js';
import {
  parseTradeableUniverseConfig,
  type TradeableUniverseConfig
} from './tradeableUniverse.js';

export interface SentinelDashboardConfig {
  sessionsDir: string;
  customUniversePath: string;
  exampleUniversePath: string;
  json: boolean;
}

export interface SentinelDashboardRuntime {
  readdir(path: string): Promise<string[]>;
  readFile(path: string): Promise<string>;
  stat(path: string): Promise<{ isDirectory(): boolean; mtimeMs: number }>;
}

export interface SentinelDashboardSessionFile {
  path: string;
  mtimeMs: number;
}

export interface SentinelDashboardMarketStateSummary {
  OPEN: number;
  CLOSED: number;
  INACTIVE: number;
  UNKNOWN: number;
}

export interface SentinelDashboardLatestSessionSummary {
  path: string;
  sessionId: string;
  startedAt: string;
  endedAt: string;
  source: string;
  mode: string;
  totals: {
    ticksAttempted: number;
    usableSnapshots: number;
    quarantinedSnapshots: number;
    rejectedSnapshots: number;
  };
  marketStates: SentinelDashboardMarketStateSummary;
  replayReadiness: {
    snapshotsCount: number;
    uniqueTickers: number;
    repeatedTickersEstimate: number;
    likelyUsefulForReplay: boolean;
  };
}

export interface SentinelDashboardUniverseSummary {
  path: string;
  source: 'custom' | 'example' | 'missing';
  name?: string;
  includeTickersCount?: number;
  includedTickersPreview?: string[];
  excludePatterns?: string[];
  excludeNonVoting?: boolean;
  maximumSpreadPercent?: number | null;
  minimumConfidence?: string | null;
  error?: string;
}

export interface SentinelDashboardSummary {
  safety: {
    atradMode: 'read-only/manual';
    autoTrading: 'disabled';
    orderPlacement: 'disabled';
    telegramLiveAlerts: 'disabled';
    supabaseLiveWrites: 'disabled';
    liveSentinelPipelineFromATrad: 'disabled';
  };
  localFiles: {
    sessionsDir: string;
    exists: boolean;
    sessionFileCount: number;
    latestSessionFilePath?: string;
    gitIgnoredWarning: string;
  };
  latestSession?: SentinelDashboardLatestSessionSummary;
  tradeableUniverse: SentinelDashboardUniverseSummary;
  recommendation: string;
}

const DEFAULT_SESSIONS_DIR = 'data/live-sessions';
const DEFAULT_CUSTOM_UNIVERSE_PATH = 'config/tradeableUniverse.json';
const DEFAULT_EXAMPLE_UNIVERSE_PATH = 'config/tradeableUniverse.example.json';
const MARKET_STATES = ['OPEN', 'CLOSED', 'INACTIVE', 'UNKNOWN'] as const;

export function createSentinelDashboardConfig(args: string[] = []): SentinelDashboardConfig {
  return {
    sessionsDir: readFlagValue(args, '--sessions-dir') ?? DEFAULT_SESSIONS_DIR,
    customUniversePath: readFlagValue(args, '--universe') ?? DEFAULT_CUSTOM_UNIVERSE_PATH,
    exampleUniversePath: readFlagValue(args, '--example-universe') ?? DEFAULT_EXAMPLE_UNIVERSE_PATH,
    json: args.includes('--json')
  };
}

export async function runSentinelDashboard(
  config: SentinelDashboardConfig = createSentinelDashboardConfig(),
  runtime: SentinelDashboardRuntime = defaultRuntime()
): Promise<SentinelDashboardSummary> {
  const sessionFiles = await listSessionFiles(config.sessionsDir, runtime);
  const latestSession = sessionFiles.latest
    ? await loadLatestSessionSummary(sessionFiles.latest.path, runtime)
    : undefined;
  const tradeableUniverse = await loadUniverseSummary(config, runtime);

  return {
    safety: {
      atradMode: 'read-only/manual',
      autoTrading: 'disabled',
      orderPlacement: 'disabled',
      telegramLiveAlerts: 'disabled',
      supabaseLiveWrites: 'disabled',
      liveSentinelPipelineFromATrad: 'disabled'
    },
    localFiles: {
      sessionsDir: config.sessionsDir,
      exists: sessionFiles.exists,
      sessionFileCount: sessionFiles.files.length,
      ...(sessionFiles.latest ? { latestSessionFilePath: sessionFiles.latest.path } : {}),
      gitIgnoredWarning: 'data/live-sessions/ is ignored by Git; do not commit session files.'
    },
    ...(latestSession ? { latestSession } : {}),
    tradeableUniverse,
    recommendation: buildDashboardRecommendation({
      latestSession,
      customUniverseExists: tradeableUniverse.source === 'custom',
      sessionsExist: sessionFiles.files.length > 0
    })
  };
}

export function formatSentinelDashboard(summary: SentinelDashboardSummary): string {
  const lines = [
    'Sentinel-CSE read-only operator dashboard',
    '',
    'Safety Status',
    `- ATrad mode: ${summary.safety.atradMode}`,
    `- auto-trading: ${summary.safety.autoTrading}`,
    `- order placement: ${summary.safety.orderPlacement}`,
    `- Telegram live alerts: ${summary.safety.telegramLiveAlerts}`,
    `- Supabase live writes: ${summary.safety.supabaseLiveWrites}`,
    `- live SentinelPipeline from ATrad: ${summary.safety.liveSentinelPipelineFromATrad}`,
    '',
    'Local Files / Sessions',
    `- sessions folder: ${summary.localFiles.sessionsDir}`,
    `- folder exists: ${summary.localFiles.exists ? 'yes' : 'no'}`,
    `- session files: ${summary.localFiles.sessionFileCount}`,
    `- latest session file: ${summary.localFiles.latestSessionFilePath ?? 'none'}`,
    `- warning: ${summary.localFiles.gitIgnoredWarning}`,
    '',
    'Latest Session Summary'
  ];

  if (!summary.latestSession) {
    lines.push('- none');
  } else {
    lines.push(`- sessionId: ${summary.latestSession.sessionId}`);
    lines.push(`- startedAt: ${summary.latestSession.startedAt}`);
    lines.push(`- endedAt: ${summary.latestSession.endedAt}`);
    lines.push(`- source: ${summary.latestSession.source}`);
    lines.push(`- mode: ${summary.latestSession.mode}`);
    lines.push(`- ticksAttempted: ${summary.latestSession.totals.ticksAttempted}`);
    lines.push(`- usableSnapshots: ${summary.latestSession.totals.usableSnapshots}`);
    lines.push(`- quarantinedSnapshots: ${summary.latestSession.totals.quarantinedSnapshots}`);
    lines.push(`- rejectedSnapshots: ${summary.latestSession.totals.rejectedSnapshots}`);
    lines.push('- market states:');
    lines.push(`- OPEN ticks: ${summary.latestSession.marketStates.OPEN}`);
    lines.push(`- CLOSED ticks: ${summary.latestSession.marketStates.CLOSED}`);
    lines.push(`- INACTIVE ticks: ${summary.latestSession.marketStates.INACTIVE}`);
    lines.push(`- UNKNOWN ticks: ${summary.latestSession.marketStates.UNKNOWN}`);
  }

  lines.push('', 'Tradeable Universe');
  lines.push(`- config path: ${summary.tradeableUniverse.path}`);
  lines.push(`- source: ${summary.tradeableUniverse.source}`);
  if (summary.tradeableUniverse.error) {
    lines.push(`- error: ${summary.tradeableUniverse.error}`);
  } else {
    lines.push(`- universe name: ${summary.tradeableUniverse.name ?? 'n/a'}`);
    lines.push(`- includeTickers count: ${summary.tradeableUniverse.includeTickersCount ?? 0}`);
    lines.push(`- included tickers preview: ${summary.tradeableUniverse.includedTickersPreview?.join(', ') || 'none'}`);
    lines.push(`- excludePatterns: ${summary.tradeableUniverse.excludePatterns?.join(', ') || 'none'}`);
    lines.push(`- excludeNonVoting: ${summary.tradeableUniverse.excludeNonVoting ? 'yes' : 'no'}`);
    lines.push(`- max spread: ${formatOptionalValue(summary.tradeableUniverse.maximumSpreadPercent)}`);
    lines.push(`- minimum confidence: ${summary.tradeableUniverse.minimumConfidence ?? 'n/a'}`);
  }

  lines.push('', 'Replay Readiness Hint');
  if (!summary.latestSession) {
    lines.push('- no latest session available');
  } else {
    lines.push(`- snapshots count: ${summary.latestSession.replayReadiness.snapshotsCount}`);
    lines.push(`- unique tickers: ${summary.latestSession.replayReadiness.uniqueTickers}`);
    lines.push(`- repeated tickers estimate: ${summary.latestSession.replayReadiness.repeatedTickersEstimate}`);
    lines.push(`- likely useful for replay: ${summary.latestSession.replayReadiness.likelyUsefulForReplay ? 'yes' : 'no'}`);
  }

  lines.push('', 'Recommended Next Action');
  lines.push(`- ${summary.recommendation}`);

  return lines.join('\n');
}

async function listSessionFiles(
  sessionsDir: string,
  runtime: SentinelDashboardRuntime
): Promise<{ exists: boolean; files: SentinelDashboardSessionFile[]; latest?: SentinelDashboardSessionFile }> {
  let entries: string[];
  try {
    const dirStat = await runtime.stat(sessionsDir);
    if (!dirStat.isDirectory()) {
      return { exists: false, files: [] };
    }
    entries = await runtime.readdir(sessionsDir);
  } catch {
    return { exists: false, files: [] };
  }

  const files: SentinelDashboardSessionFile[] = [];
  for (const entry of entries.filter((name) => name.toLowerCase().endsWith('.json'))) {
    const path = join(sessionsDir, entry);
    try {
      const fileStat = await runtime.stat(path);
      files.push({ path, mtimeMs: fileStat.mtimeMs });
    } catch {
      // A file can disappear between readdir and stat; ignore that race.
    }
  }

  files.sort((left, right) => right.mtimeMs - left.mtimeMs || right.path.localeCompare(left.path));
  return {
    exists: true,
    files,
    ...(files[0] ? { latest: files[0] } : {})
  };
}

async function loadLatestSessionSummary(
  path: string,
  runtime: SentinelDashboardRuntime
): Promise<SentinelDashboardLatestSessionSummary> {
  const session = parseATradRecordedSessionFile(await runtime.readFile(path));
  const snapshots = extractReplayableATradSnapshots(session);
  const tickerCounts = new Map<string, number>();
  snapshots.forEach((snapshot) => {
    tickerCounts.set(snapshot.ticker, (tickerCounts.get(snapshot.ticker) ?? 0) + 1);
  });

  return {
    path,
    sessionId: session.sessionId,
    startedAt: session.startedAt,
    endedAt: session.endedAt,
    source: session.source,
    mode: session.mode,
    totals: {
      ticksAttempted: session.totals?.ticksAttempted ?? 0,
      usableSnapshots: session.totals?.usableSnapshots ?? snapshots.length,
      quarantinedSnapshots: session.totals?.quarantinedSnapshots ?? 0,
      rejectedSnapshots: session.totals?.rejectedSnapshots ?? 0
    },
    marketStates: summarizeMarketStates(session),
    replayReadiness: {
      snapshotsCount: snapshots.length,
      uniqueTickers: tickerCounts.size,
      repeatedTickersEstimate: [...tickerCounts.values()].filter((count) => count >= 2).length,
      likelyUsefulForReplay: snapshots.length > 0 && [...tickerCounts.values()].some((count) => count >= 2)
    }
  };
}

async function loadUniverseSummary(
  config: SentinelDashboardConfig,
  runtime: SentinelDashboardRuntime
): Promise<SentinelDashboardUniverseSummary> {
  const customUniverse = await tryLoadUniverse(config.customUniversePath, 'custom', runtime);
  if (customUniverse.source !== 'missing') {
    return customUniverse;
  }

  return tryLoadUniverse(config.exampleUniversePath, 'example', runtime);
}

async function tryLoadUniverse(
  path: string,
  source: 'custom' | 'example',
  runtime: SentinelDashboardRuntime
): Promise<SentinelDashboardUniverseSummary> {
  try {
    const universe = parseTradeableUniverseConfig(await runtime.readFile(path), path);
    return buildUniverseSummary(path, source, universe);
  } catch (error) {
    if (isFileMissingError(error)) {
      return { path, source: 'missing' };
    }
    const message = error instanceof Error ? error.message : String(error);
    return { path, source, error: message };
  }
}

function buildUniverseSummary(
  path: string,
  source: 'custom' | 'example',
  universe: TradeableUniverseConfig
): SentinelDashboardUniverseSummary {
  return {
    path,
    source,
    name: universe.name,
    includeTickersCount: universe.includeTickers.length,
    includedTickersPreview: universe.includeTickers.slice(0, 5),
    excludePatterns: universe.excludePatterns,
    excludeNonVoting: universe.rules.excludeNonVoting,
    maximumSpreadPercent: universe.rules.maximumSpreadPercent,
    minimumConfidence: universe.rules.minimumConfidence
  };
}

function summarizeMarketStates(session: ATradRecordedSession): SentinelDashboardMarketStateSummary {
  const counts: SentinelDashboardMarketStateSummary = {
    OPEN: 0,
    CLOSED: 0,
    INACTIVE: 0,
    UNKNOWN: 0
  };

  for (const diagnostic of session.diagnostics ?? []) {
    const marketState = isMarketState(diagnostic.marketState) ? diagnostic.marketState : 'UNKNOWN';
    counts[marketState] += 1;
  }

  return counts;
}

function buildDashboardRecommendation(input: {
  latestSession?: SentinelDashboardLatestSessionSummary;
  customUniverseExists: boolean;
  sessionsExist: boolean;
}): string {
  if (!input.sessionsExist || !input.latestSession) {
    return 'Record an open-market ATrad session with pnpm atrad:record-session.';
  }

  const marketStates = input.latestSession.marketStates;
  if (
    marketStates.CLOSED > 0 &&
    marketStates.OPEN === 0 &&
    marketStates.INACTIVE === 0 &&
    marketStates.UNKNOWN === 0
  ) {
    return 'Record during market open; the latest session contains only CLOSED ticks.';
  }

  if (!input.customUniverseExists) {
    return 'Create config/tradeableUniverse.json from the example before focused replay research.';
  }

  if (input.latestSession.totals.usableSnapshots > 0) {
    return `Replay the latest session with --universe config/tradeableUniverse.json: ${input.latestSession.path}`;
  }

  return 'Record a longer open-market session with usable snapshots.';
}

function isMarketState(value: unknown): value is keyof SentinelDashboardMarketStateSummary {
  return typeof value === 'string' && MARKET_STATES.includes(value as keyof SentinelDashboardMarketStateSummary);
}

function isFileMissingError(error: unknown): boolean {
  return error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'ENOENT';
}

function formatOptionalValue(value: number | null | undefined): string {
  return value === null || value === undefined ? 'n/a' : String(value);
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function defaultRuntime(): SentinelDashboardRuntime {
  return {
    readdir: async (path) => readdir(path),
    readFile: async (path) => readFile(path, 'utf8'),
    stat: async (path) => stat(path)
  };
}
