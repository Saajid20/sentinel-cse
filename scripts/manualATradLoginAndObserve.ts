import { mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import {
  ATRAD_STORAGE_STATE_PATH,
  DEFAULT_ATRAD_BASE_URL,
  isSafeStorageStatePath
} from './manualATradLogin.js';
import {
  collectPageDiagnostics,
  debugMarketWatchRows,
  extractFullGridMarketWatchRows,
  extractVisibleMarketWatchRows,
  formatObserveOnceSummary,
  partitionATradSnapshotsByConfidence,
  sanitizeMarketWatchRows,
  type ManualATradPageLike,
  type ManualATradObserveOnceResult
} from './manualATradObserveOnce.js';

const LOGIN_AND_OBSERVE_NAVIGATION_TIMEOUT_MS = 30_000;

export interface ManualATradLoginAndObserveConfig {
  baseUrl: string;
  storageStatePath: string;
  diagnose: boolean;
  debugRows: boolean;
  fullGridScan: boolean;
  headless: false;
  readonlyMode: true;
}

export interface ManualATradLoginAndObserveRuntime {
  launchSession(config: ManualATradLoginAndObserveConfig): Promise<ManualATradLoginAndObserveSessionResource>;
  waitForUser(): Promise<void>;
  now(): number;
  log(message: string): void;
}

export interface ManualATradLoginAndObserveSessionLike {
  pages(): ManualATradPageLike[];
  newPage(): Promise<ManualATradPageLike>;
  storageState(options: { path: string }): Promise<void>;
}

export interface ManualATradLoginAndObserveSessionResource {
  session: ManualATradLoginAndObserveSessionLike;
  close(): Promise<void>;
}

export function createManualATradLoginAndObserveConfig(
  args: string[] = []
): ManualATradLoginAndObserveConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    diagnose: args.includes('--diagnose'),
    debugRows: args.includes('--debug-rows'),
    fullGridScan: args.includes('--full-grid-scan'),
    headless: false,
    readonlyMode: true
  };
}

export function formatManualATradLoginAndObserveInstructions(
  config: ManualATradLoginAndObserveConfig
): string[] {
  return [
    'Sentinel-CSE same-session ATrad login-and-observe',
    `Opening: ${config.baseUrl}`,
    '',
    'Log in manually, complete 2FA if needed, navigate to Market Watch/home page, then return to this terminal and press Enter.',
    'If needed, manually select "Full Watch - Equity" in the Market Watch area before pressing Enter.',
    'No credentials are read by this script, and no form fields are automated.',
    `Storage state will be saved to: ${config.storageStatePath}`
  ];
}

export async function runManualATradLoginAndObserve(
  config: ManualATradLoginAndObserveConfig = createManualATradLoginAndObserveConfig(),
  runtime: ManualATradLoginAndObserveRuntime = defaultRuntime()
): Promise<ManualATradObserveOnceResult> {
  if (config.readonlyMode !== true || config.headless !== false) {
    throw new Error('Manual ATrad login-and-observe must run visibly with readonlyMode: true.');
  }

  if (!isSafeStorageStatePath(config.storageStatePath)) {
    throw new Error(`Unsafe storage state path: ${config.storageStatePath}`);
  }

  assertATradReadOnlySafety('manual read-only login and observe session');

  await mkdir(dirname(config.storageStatePath), { recursive: true });
  const resource = await runtime.launchSession(config);

  try {
    const initialPage = resource.session.pages()[0] ?? (await resource.session.newPage());
    await initialPage.goto(config.baseUrl, {
      waitUntil: 'domcontentloaded',
      timeout: LOGIN_AND_OBSERVE_NAVIGATION_TIMEOUT_MS
    });

    for (const line of formatManualATradLoginAndObserveInstructions(config)) {
      runtime.log(line);
    }

    await runtime.waitForUser();
    await saveStorageState(resource.session, config.storageStatePath);

    const observationPage = getActivePage(resource.session, initialPage);
    const result = config.diagnose
      ? await runDiagnostics(observationPage)
      : config.debugRows
        ? await debugMarketWatchRows(observationPage, runtime.now())
        : await runExtraction(observationPage, runtime.now(), config.fullGridScan);

    for (const line of formatObserveOnceSummary(result)) {
      runtime.log(line);
    }

    return result;
  } finally {
    await resource.close();
  }
}

function getActivePage(
  session: ManualATradLoginAndObserveSessionLike,
  fallback: ManualATradPageLike
): ManualATradPageLike {
  const pages = session.pages();
  return pages.length > 0 ? pages[pages.length - 1] ?? fallback : fallback;
}

async function runDiagnostics(
  page: ManualATradPageLike
): Promise<ManualATradObserveOnceResult> {
  const diagnostics = await collectPageDiagnostics(page);
  return {
    ok: true,
    message: 'ATrad same-session read-only diagnostics completed.',
    rawRows: [],
    rawSnapshots: [],
    rowResults: [],
    accepted: [],
    rejected: [],
    diagnostics,
    qualityAssessments: [],
    qualitySummary: {
      highConfidence: 0,
      mediumConfidence: 0,
      lowConfidence: 0,
      rejected: 0
    },
    usableSnapshots: [],
    quarantinedSnapshots: [],
    rejectedSnapshots: [],
    usablePolicy: 'HIGH_CONFIDENCE only'
  };
}

async function runExtraction(
  page: ManualATradPageLike,
  timestamp: number,
  fullGridScan: boolean
): Promise<ManualATradObserveOnceResult> {
  const scan = fullGridScan ? await extractFullGridMarketWatchRows(page) : undefined;
  const rawRows = scan?.rows ?? await extractVisibleMarketWatchRows(page);
  const sanitized = sanitizeMarketWatchRows(rawRows, timestamp);
  const partition = partitionATradSnapshotsByConfidence(
    sanitized.rowResults,
    sanitized.qualityAssessments
  );
  return {
    ok: true,
    message: 'ATrad same-session read-only snapshot completed.',
    rawRows,
    fullGridScan: scan?.diagnostics,
    ...sanitized,
    ...partition
  };
}

function parseBaseUrl(args: string[]): string {
  const flagIndex = args.findIndex((arg) => arg === '--base-url');
  const candidate = flagIndex >= 0 ? args[flagIndex + 1] : args.find((arg) => !arg.startsWith('--'));
  const baseUrl = candidate?.trim() || DEFAULT_ATRAD_BASE_URL;

  try {
    return new URL(baseUrl).toString();
  } catch {
    throw new Error(`Invalid ATrad base URL: ${baseUrl}`);
  }
}

function defaultRuntime(): ManualATradLoginAndObserveRuntime {
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
    log: (message) => console.log(message)
  };
}

async function saveStorageState(session: ManualATradLoginAndObserveSessionLike, path: string): Promise<void> {
  assertATradReadOnlySafety('save read-only browser storage state');
  await session.storageState({ path });
}

async function main(): Promise<void> {
  const result = await runManualATradLoginAndObserve(
    createManualATradLoginAndObserveConfig(process.argv.slice(2))
  );
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad login-and-observe failed: ${message}`);
    process.exitCode = 1;
  });
}
