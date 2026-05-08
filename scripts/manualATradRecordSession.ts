import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import type { MarketSnapshot } from '../packages/core/src/index.js';
import { DEFAULT_ATRAD_BASE_URL } from './manualATradLogin.js';
import {
  extractVisibleMarketWatchRows,
  partitionATradSnapshotsByConfidence,
  sanitizeMarketWatchRows,
  type ATradParsedRowQualityAssessment,
  type ATradParsedRowQualityStatus,
  type ManualATradPageLike,
  type SanitizedObservedMarketWatchRow
} from './manualATradObserveOnce.js';

const RECORDING_NAVIGATION_TIMEOUT_MS = 30_000;
export const DEFAULT_ATRAD_RECORDING_INTERVAL_SECONDS = 15;
export const DEFAULT_ATRAD_RECORDING_DURATION_SECONDS = 60;
export const DEFAULT_ATRAD_RECORDING_OUTPUT_DIR = 'data/live-sessions';
export const ATRAD_RECORDING_SOURCE = 'atrad-full-watch-equity';
export const ATRAD_RECORDING_MODE = 'read-only-local-recording';

export interface ManualATradRecordSessionConfig {
  baseUrl: string;
  durationSeconds: number;
  intervalSeconds: number;
  outputPath: string;
  allowMediumConfidence: boolean;
  includeQuarantined: boolean;
  maxTicks?: number;
  headless: false;
  readonlyMode: true;
}

export interface RecordedATradSnapshot extends MarketSnapshot {
  source: string;
  metadata?: Record<string, unknown>;
}

export interface ATradSessionTickDiagnostic {
  tickNumber: number;
  capturedAt: string;
  rawRowsExtracted: number;
  acceptedSnapshots: number;
  usableSnapshots: number;
  quarantinedSnapshots: number;
  rejectedSnapshots: number;
}

export interface QuarantinedATradSnapshotDiagnostic {
  tickNumber: number;
  ticker?: string;
  status: ATradParsedRowQualityStatus;
  issueCodes: string[];
}

export interface ATradRecordedSession {
  sessionId: string;
  startedAt: string;
  endedAt: string;
  source: typeof ATRAD_RECORDING_SOURCE;
  mode: typeof ATRAD_RECORDING_MODE;
  confidencePolicy: 'HIGH_CONFIDENCE only' | 'HIGH_CONFIDENCE + MEDIUM_CONFIDENCE';
  intervalSeconds: number;
  durationSeconds: number;
  totals: {
    ticksAttempted: number;
    rawRowsExtracted: number;
    usableSnapshots: number;
    quarantinedSnapshots: number;
    rejectedSnapshots: number;
  };
  snapshots: RecordedATradSnapshot[];
  diagnostics: ATradSessionTickDiagnostic[];
  quarantinedRows?: QuarantinedATradSnapshotDiagnostic[];
}

export interface ManualATradRecordSessionResult {
  ok: boolean;
  message: string;
  outputPath: string;
  session: ATradRecordedSession;
}

export interface ManualATradRecordSessionSessionLike {
  pages(): ManualATradPageLike[];
  newPage(): Promise<ManualATradPageLike>;
}

export interface ManualATradRecordSessionSessionResource {
  session: ManualATradRecordSessionSessionLike;
  close(): Promise<void>;
}

export interface ManualATradRecordSessionRuntime {
  launchSession(config: ManualATradRecordSessionConfig): Promise<ManualATradRecordSessionSessionResource>;
  waitForUser(): Promise<void>;
  now(): number;
  sleep(ms: number): Promise<void>;
  ensureDir(path: string): Promise<void>;
  writeFile(path: string, contents: string): Promise<void>;
  log(message: string): void;
}

interface ATradRecordingTickCapture {
  timestamp: number;
  rawRowsExtracted: number;
  acceptedCount: number;
  usableRows: SanitizedObservedMarketWatchRow[];
  quarantinedRows: SanitizedObservedMarketWatchRow[];
  rejectedRows: SanitizedObservedMarketWatchRow[];
  usablePolicy: ATradRecordedSession['confidencePolicy'];
  qualityAssessments: ATradParsedRowQualityAssessment[];
}

export function createManualATradRecordSessionConfig(
  args: string[] = [],
  now: number = Date.now()
): ManualATradRecordSessionConfig {
  const outputArg = readFlagValue(args, '--output');
  return {
    baseUrl: parseBaseUrl(args),
    durationSeconds: parsePositiveIntegerFlag(args, '--duration-seconds', DEFAULT_ATRAD_RECORDING_DURATION_SECONDS),
    intervalSeconds: parsePositiveIntegerFlag(args, '--interval-seconds', DEFAULT_ATRAD_RECORDING_INTERVAL_SECONDS),
    outputPath: buildATradRecordSessionOutputPath(now, outputArg),
    allowMediumConfidence: args.includes('--allow-medium-confidence'),
    includeQuarantined: args.includes('--include-quarantined'),
    maxTicks: parseOptionalPositiveIntegerFlag(args, '--max-ticks'),
    headless: false,
    readonlyMode: true
  };
}

export function buildATradRecordSessionOutputPath(now: number, outputArg?: string): string {
  const timestamp = formatTimestampForFile(now);
  const fileName = `atrad-session-${timestamp}.json`;

  if (!outputArg) {
    return `${DEFAULT_ATRAD_RECORDING_OUTPUT_DIR}/${fileName}`;
  }

  const trimmed = outputArg.trim().replace(/\\/g, '/');
  if (trimmed.toLowerCase().endsWith('.json')) {
    return trimmed;
  }

  return `${trimmed.replace(/\/+$/, '')}/${fileName}`;
}

export function formatManualATradRecordSessionInstructions(
  config: ManualATradRecordSessionConfig
): string[] {
  return [
    'Sentinel-CSE local ATrad live session recorder',
    `Opening: ${config.baseUrl}`,
    '',
    'Log in manually, complete 2FA if needed, and manually select "Full Watch - Equity" before recording.',
    'When the market watch page is ready, return to this terminal and press Enter to begin recording.',
    'This recorder is read-only and does not automate credentials, place orders, or run the strategy pipeline.',
    `Recording output: ${config.outputPath}`,
    `Interval: ${config.intervalSeconds}s`,
    `Duration: ${config.durationSeconds}s`,
    `Confidence policy: ${config.allowMediumConfidence ? 'HIGH_CONFIDENCE + MEDIUM_CONFIDENCE' : 'HIGH_CONFIDENCE only'}`
  ];
}

export async function captureATradRecordingTick(
  page: ManualATradPageLike,
  timestamp: number,
  options: { allowMediumConfidence?: boolean } = {}
): Promise<ATradRecordingTickCapture> {
  const rawRows = await extractVisibleMarketWatchRows(page);
  const sanitized = sanitizeMarketWatchRows(rawRows, timestamp);
  const partition = partitionATradSnapshotsByConfidence(
    sanitized.rowResults,
    sanitized.qualityAssessments,
    { allowMediumConfidence: options.allowMediumConfidence }
  );

  return {
    timestamp,
    rawRowsExtracted: rawRows.length,
    acceptedCount: sanitized.accepted.length,
    usableRows: partition.usableSnapshots,
    quarantinedRows: partition.quarantinedSnapshots,
    rejectedRows: partition.rejectedSnapshots,
    usablePolicy: partition.usablePolicy,
    qualityAssessments: sanitized.qualityAssessments
  };
}

export function buildRecordedATradSnapshot(row: SanitizedObservedMarketWatchRow): RecordedATradSnapshot {
  if (!row.snapshot) {
    throw new Error('Cannot record a snapshot that was not accepted by the sanitizer.');
  }

  return {
    ...row.snapshot,
    source: typeof row.rawSnapshot.source === 'string' ? row.rawSnapshot.source : ATRAD_RECORDING_SOURCE,
    metadata: isRecordMetadata(row.rawSnapshot.metadata) ? row.rawSnapshot.metadata : undefined
  };
}

export async function runManualATradRecordSession(
  config: ManualATradRecordSessionConfig = createManualATradRecordSessionConfig(),
  runtime: ManualATradRecordSessionRuntime = defaultRuntime()
): Promise<ManualATradRecordSessionResult> {
  if (config.readonlyMode !== true || config.headless !== false) {
    throw new Error('Manual ATrad session recording must run visibly with readonlyMode: true.');
  }

  assertATradReadOnlySafety('manual read-only ATrad live session recording');

  await runtime.ensureDir(dirname(config.outputPath));
  const resource = await runtime.launchSession(config);
  const startedAtMs = runtime.now();
  const sessionId = buildSessionId(startedAtMs);
  const stopAtMs = startedAtMs + config.durationSeconds * 1000;
  const session: ATradRecordedSession = {
    sessionId,
    startedAt: new Date(startedAtMs).toISOString(),
    endedAt: new Date(startedAtMs).toISOString(),
    source: ATRAD_RECORDING_SOURCE,
    mode: ATRAD_RECORDING_MODE,
    confidencePolicy: config.allowMediumConfidence
      ? 'HIGH_CONFIDENCE + MEDIUM_CONFIDENCE'
      : 'HIGH_CONFIDENCE only',
    intervalSeconds: config.intervalSeconds,
    durationSeconds: config.durationSeconds,
    totals: {
      ticksAttempted: 0,
      rawRowsExtracted: 0,
      usableSnapshots: 0,
      quarantinedSnapshots: 0,
      rejectedSnapshots: 0
    },
    snapshots: [],
    diagnostics: [],
    ...(config.includeQuarantined ? { quarantinedRows: [] } : {})
  };

  try {
    const initialPage = resource.session.pages()[0] ?? (await resource.session.newPage());
    await initialPage.goto(config.baseUrl, {
      waitUntil: 'domcontentloaded',
      timeout: RECORDING_NAVIGATION_TIMEOUT_MS
    });

    for (const line of formatManualATradRecordSessionInstructions(config)) {
      runtime.log(line);
    }

    await runtime.waitForUser();

    let tickNumber = 0;
    while (true) {
      const now = runtime.now();
      if (config.maxTicks !== undefined && tickNumber >= config.maxTicks) {
        break;
      }

      if (tickNumber > 0 && now >= stopAtMs) {
        break;
      }

      tickNumber += 1;
      const activePage = getActivePage(resource.session, initialPage);
      const capture = await captureATradRecordingTick(activePage, now, {
        allowMediumConfidence: config.allowMediumConfidence
      });

      session.totals.ticksAttempted += 1;
      session.totals.rawRowsExtracted += capture.rawRowsExtracted;
      session.totals.usableSnapshots += capture.usableRows.length;
      session.totals.quarantinedSnapshots += capture.quarantinedRows.length;
      session.totals.rejectedSnapshots += capture.rejectedRows.length;
      session.snapshots.push(...capture.usableRows.map(buildRecordedATradSnapshot));
      session.diagnostics.push({
        tickNumber,
        capturedAt: new Date(capture.timestamp).toISOString(),
        rawRowsExtracted: capture.rawRowsExtracted,
        acceptedSnapshots: capture.acceptedCount,
        usableSnapshots: capture.usableRows.length,
        quarantinedSnapshots: capture.quarantinedRows.length,
        rejectedSnapshots: capture.rejectedRows.length
      });

      if (config.includeQuarantined && session.quarantinedRows) {
        capture.quarantinedRows.forEach((row, index) => {
          const assessment = capture.qualityAssessments.find(
            (entry) => entry.row === row.row || entry.rawSnapshot === row.rawSnapshot
          ) ?? capture.qualityAssessments[index];
          session.quarantinedRows?.push({
            tickNumber,
            ticker: row.snapshot?.ticker ?? asTicker(row.rawSnapshot.ticker),
            status: assessment?.status ?? 'LOW_CONFIDENCE',
            issueCodes: assessment?.issues.map((issue) => issue.code) ?? []
          });
        });
      }

      runtime.log(
        `Tick ${tickNumber}: usable=${capture.usableRows.length}, quarantined=${capture.quarantinedRows.length}, rejected=${capture.rejectedRows.length}`
      );

      if (config.maxTicks !== undefined && tickNumber >= config.maxTicks) {
        break;
      }

      if (runtime.now() >= stopAtMs) {
        break;
      }

      await runtime.sleep(config.intervalSeconds * 1000);
    }

    session.endedAt = new Date(runtime.now()).toISOString();
    await runtime.writeFile(config.outputPath, JSON.stringify(session, null, 2));

    const message = `ATrad live session recording saved to ${config.outputPath}`;
    runtime.log(message);
    return {
      ok: true,
      message,
      outputPath: config.outputPath,
      session
    };
  } finally {
    await resource.close();
  }
}

function getActivePage(
  session: ManualATradRecordSessionSessionLike,
  fallback: ManualATradPageLike
): ManualATradPageLike {
  const pages = session.pages();
  return pages.length > 0 ? pages[pages.length - 1] ?? fallback : fallback;
}

function buildSessionId(now: number): string {
  return `atrad-session-${formatTimestampForFile(now)}`;
}

function formatTimestampForFile(now: number): string {
  const date = new Date(now);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  const seconds = String(date.getUTCSeconds()).padStart(2, '0');
  return `${year}${month}${day}-${hours}${minutes}${seconds}`;
}

function parseBaseUrl(args: string[]): string {
  const candidate = readFlagValue(args, '--base-url');
  const baseUrl = candidate?.trim() || DEFAULT_ATRAD_BASE_URL;

  try {
    return new URL(baseUrl).toString();
  } catch {
    throw new Error(`Invalid ATrad base URL: ${baseUrl}`);
  }
}

function parsePositiveIntegerFlag(args: string[], flag: string, fallback: number): number {
  const value = readFlagValue(args, flag);
  if (value === undefined) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid ${flag} value: ${value}`);
  }

  return parsed;
}

function parseOptionalPositiveIntegerFlag(args: string[], flag: string): number | undefined {
  const value = readFlagValue(args, flag);
  if (value === undefined) {
    return undefined;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid ${flag} value: ${value}`);
  }

  return parsed;
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function isRecordMetadata(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asTicker(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function defaultRuntime(): ManualATradRecordSessionRuntime {
  return {
    launchSession: async (config) => {
      const browser = await chromium.launch({ headless: config.headless });
      const context = await browser.newContext();
      return {
        session: context,
        close: async () => browser.close()
      };
    },
    waitForUser: async () => {
      const readline = createInterface({ input, output });
      try {
        await readline.question('');
      } finally {
        readline.close();
      }
    },
    now: () => Date.now(),
    sleep: async (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    ensureDir: async (path) => {
      await mkdir(path, { recursive: true });
    },
    writeFile: async (path, contents) => {
      await writeFile(path, contents, 'utf8');
    },
    log: (message) => console.log(message)
  };
}

async function main(): Promise<void> {
  const result = await runManualATradRecordSession(
    createManualATradRecordSessionConfig(process.argv.slice(2))
  );
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad record-session failed: ${message}`);
    process.exitCode = 1;
  });
}
