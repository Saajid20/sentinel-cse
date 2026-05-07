import { access } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import { MarketDataSanitizer } from '../packages/core/src/index.js';
import type {
  MarketDataSanitizationIssue,
  MarketSnapshot,
  RawMarketSnapshot
} from '../packages/core/src/index.js';
import { ATRAD_STORAGE_STATE_PATH } from './manualATradLogin.js';

export const DEFAULT_ATRAD_MARKET_WATCH_URL = 'https://example.invalid/atrad-market-watch';
export const ATRAD_MARKET_WATCH_SOURCE = 'atrad-market-watch';

const MARKET_WATCH_HEADERS = [
  'Security',
  'Bid Qty',
  'Bid Price',
  'Ask Price',
  'Ask Qty',
  'Last',
  'Last Qty',
  'Change',
  '% Change',
  'High',
  'Low',
  'VWA',
  'Volume',
  'Turnover',
  'Trades',
  'Time'
];

export type MarketWatchRow = Record<string, string>;

export interface ManualATradObserveOnceConfig {
  baseUrl: string;
  storageStatePath: string;
  headless: boolean;
  observationTimeoutMs: number;
  readonlyMode: true;
}

export interface ManualATradBrowserLike {
  newContext(options: { storageState: string }): Promise<ManualATradContextLike>;
  close(): Promise<void>;
}

export interface ManualATradContextLike {
  newPage(): Promise<ManualATradPageLike>;
}

export interface ManualATradPageLike {
  goto(url: string, options: { waitUntil: 'domcontentloaded'; timeout: number }): Promise<void>;
  evaluate<T>(pageFunction: string | (() => T)): Promise<T>;
}

export interface ManualATradObserveOnceRuntime {
  storageStateExists(path: string): Promise<boolean>;
  launchBrowser(config: ManualATradObserveOnceConfig): Promise<ManualATradBrowserLike>;
  now(): number;
  log(message: string): void;
}

export interface SanitizedObservedMarketWatchRow {
  rawSnapshot: RawMarketSnapshot;
  snapshot?: MarketSnapshot;
  issues: MarketDataSanitizationIssue[];
}

export interface ManualATradObserveOnceResult {
  ok: boolean;
  message: string;
  rawRows: MarketWatchRow[];
  rawSnapshots: RawMarketSnapshot[];
  accepted: SanitizedObservedMarketWatchRow[];
  rejected: SanitizedObservedMarketWatchRow[];
}

export function createManualATradObserveOnceConfig(args: string[] = []): ManualATradObserveOnceConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    headless: args.includes('--headless'),
    observationTimeoutMs: parseTimeoutMs(args),
    readonlyMode: true
  };
}

export function marketWatchRowToRawSnapshot(
  row: MarketWatchRow,
  timestamp: number
): RawMarketSnapshot {
  return {
    ticker: field(row, 'Security'),
    lastPrice: field(row, 'Last'),
    bestBid: field(row, 'Bid Price'),
    bestAsk: field(row, 'Ask Price'),
    bidDepth: field(row, 'Bid Qty'),
    askDepth: field(row, 'Ask Qty'),
    volume: field(row, 'Volume'),
    totalTurnover: field(row, 'Turnover'),
    timestamp,
    source: ATRAD_MARKET_WATCH_SOURCE,
    metadata: {
      high: field(row, 'High'),
      low: field(row, 'Low'),
      vwa: field(row, 'VWA'),
      trades: field(row, 'Trades'),
      time: field(row, 'Time'),
      lastQty: field(row, 'Last Qty'),
      change: field(row, 'Change'),
      percentChange: field(row, '% Change'),
      rawRow: { ...row }
    }
  };
}

export function sanitizeMarketWatchRows(
  rows: MarketWatchRow[],
  timestamp: number,
  sanitizer: MarketDataSanitizer = new MarketDataSanitizer({ source: ATRAD_MARKET_WATCH_SOURCE })
): Pick<ManualATradObserveOnceResult, 'rawSnapshots' | 'accepted' | 'rejected'> {
  const rawSnapshots = rows.map((row) => marketWatchRowToRawSnapshot(row, timestamp));
  const accepted: SanitizedObservedMarketWatchRow[] = [];
  const rejected: SanitizedObservedMarketWatchRow[] = [];

  for (const rawSnapshot of rawSnapshots) {
    const result = sanitizer.sanitize(rawSnapshot);
    const rowResult: SanitizedObservedMarketWatchRow = {
      rawSnapshot,
      snapshot: result.snapshot,
      issues: result.issues
    };

    if (result.accepted) {
      accepted.push(rowResult);
    } else {
      rejected.push(rowResult);
    }
  }

  return {
    rawSnapshots,
    accepted,
    rejected
  };
}

export async function runManualATradObserveOnce(
  config: ManualATradObserveOnceConfig = createManualATradObserveOnceConfig(),
  runtime: ManualATradObserveOnceRuntime = defaultRuntime()
): Promise<ManualATradObserveOnceResult> {
  if (config.readonlyMode !== true) {
    throw new Error('Manual ATrad observe-once requires readonlyMode: true.');
  }

  assertATradReadOnlySafety('read Market Watch table data');

  if (!(await runtime.storageStateExists(config.storageStatePath))) {
    const message = `ATrad storage state is missing or expired. Run pnpm atrad:login first. Expected: ${config.storageStatePath}`;
    runtime.log(message);
    return emptyResult(false, message);
  }

  const browser = await runtime.launchBrowser(config);
  try {
    const context = await browser.newContext({ storageState: config.storageStatePath });
    const page = await context.newPage();
    await page.goto(config.baseUrl, {
      waitUntil: 'domcontentloaded',
      timeout: config.observationTimeoutMs
    });

    const rawRows = await extractVisibleMarketWatchRows(page);
    const sanitized = sanitizeMarketWatchRows(rawRows, runtime.now());
    const result: ManualATradObserveOnceResult = {
      ok: true,
      message: 'ATrad observe-once read-only snapshot completed.',
      rawRows,
      ...sanitized
    };

    for (const line of formatObserveOnceSummary(result)) {
      runtime.log(line);
    }

    return result;
  } finally {
    await browser.close();
  }
}

export async function extractVisibleMarketWatchRows(page: ManualATradPageLike): Promise<MarketWatchRow[]> {
  assertATradReadOnlySafety('read visible Market Watch table rows');

  return page.evaluate<MarketWatchRow[]>(BROWSER_SAFE_MARKET_WATCH_EVALUATION);
}

export function formatObserveOnceSummary(result: ManualATradObserveOnceResult): string[] {
  return [
    'Sentinel-CSE ATrad observe-once read-only summary',
    `Raw rows extracted: ${result.rawRows.length}`,
    JSON.stringify(result.rawRows, null, 2),
    `Accepted snapshots: ${result.accepted.length}`,
    `Rejected snapshots: ${result.rejected.length}`,
    ...result.rejected.flatMap((row, index) => [
      `Rejected row ${index + 1}: ${String(row.rawSnapshot.ticker ?? 'unknown')}`,
      ...row.issues.map((issue) => `- ${issue.code}: ${issue.message}`)
    ])
  ];
}

function parseBaseUrl(args: string[]): string {
  const flagIndex = args.findIndex((arg) => arg === '--base-url');
  const candidate = flagIndex >= 0 ? args[flagIndex + 1] : args.find((arg) => !arg.startsWith('--'));
  const baseUrl = candidate?.trim() || DEFAULT_ATRAD_MARKET_WATCH_URL;

  try {
    return new URL(baseUrl).toString();
  } catch {
    throw new Error(`Invalid ATrad base URL: ${baseUrl}`);
  }
}

function parseTimeoutMs(args: string[]): number {
  const flagIndex = args.findIndex((arg) => arg === '--timeout-ms');
  const raw = flagIndex >= 0 ? args[flagIndex + 1] : undefined;
  const timeout = raw === undefined ? 30_000 : Number(raw);
  return Number.isFinite(timeout) && timeout > 0 ? timeout : 30_000;
}

function field(row: MarketWatchRow, name: string): string | undefined {
  const value = row[name]?.trim();
  return value && value.length > 0 ? value : undefined;
}

function emptyResult(ok: boolean, message: string): ManualATradObserveOnceResult {
  return {
    ok,
    message,
    rawRows: [],
    rawSnapshots: [],
    accepted: [],
    rejected: []
  };
}

function defaultRuntime(): ManualATradObserveOnceRuntime {
  return {
    storageStateExists: async (path) => {
      try {
        await access(path);
        return true;
      } catch {
        return false;
      }
    },
    launchBrowser: async (config) => chromium.launch({ headless: config.headless }),
    now: () => Date.now(),
    log: (message) => console.log(message)
  };
}

const BROWSER_SAFE_MARKET_WATCH_EVALUATION = `(() => {
  const allowedHeaders = ${JSON.stringify(MARKET_WATCH_HEADERS)};

  function normalize(value) {
    return String(value || '').replace(/\\s+/g, ' ').trim();
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  const tables = Array.from(document.querySelectorAll('table')).filter(isVisible);
  for (const table of tables) {
    const tableRows = Array.from(table.querySelectorAll('tr')).filter(isVisible);
    if (tableRows.length < 2) {
      continue;
    }

    const headerCells = Array.from(tableRows[0].querySelectorAll('th,td'));
    const headers = headerCells.map((cell) => normalize(cell.textContent));
    const allowedHeaderCount = headers.filter((header) => allowedHeaders.includes(header)).length;
    if (!headers.includes('Security') || allowedHeaderCount < 3) {
      continue;
    }

    return tableRows
      .slice(1)
      .map((row) => {
        const cells = Array.from(row.querySelectorAll('td'));
        const mapped = {};
        headers.forEach((header, index) => {
          if (allowedHeaders.includes(header)) {
            mapped[header] = normalize(cells[index] ? cells[index].textContent : '');
          }
        });
        return mapped;
      })
      .filter((row) => Object.values(row).some((value) => String(value).length > 0));
  }

  return [];
})()`;

async function main(): Promise<void> {
  const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(process.argv.slice(2)));
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad observe-once failed: ${message}`);
    process.exitCode = 1;
  });
}
