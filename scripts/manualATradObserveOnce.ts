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
import {
  ATRAD_PERSISTENT_PROFILE_PATH,
  ATRAD_STORAGE_STATE_PATH,
  isSafePersistentProfilePath,
  isSafeStorageStatePath
} from './manualATradLogin.js';

export const DEFAULT_ATRAD_MARKET_WATCH_URL = 'https://example.invalid/atrad-market-watch';
export const ATRAD_MARKET_WATCH_SOURCE = 'atrad-market-watch';

const MARKET_WATCH_HEADERS = [
  'Security',
  'Company Name',
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
  'Price Close',
  'Buy Sentiment',
  'Time'
];

const DIAGNOSTIC_KEYWORDS = [
  'Market',
  'Watch',
  'Security',
  'Bid',
  'Ask',
  'Volume',
  'Turnover',
  'Last',
  'Trades'
];

const PREFERRED_MARKET_WATCH_KEYWORDS = [
  'Market Watch',
  'Full Watch',
  'Equity',
  'Security',
  'Bid Qty',
  'Bid Price',
  'Ask Price',
  'Ask Qty',
  'Last',
  'Volume',
  'Turnover'
];

const DIAGNOSTIC_VISIBLE_TEXT_LIMIT = 30;

export type MarketWatchRow = Record<string, string>;

export interface ManualATradObserveOnceConfig {
  baseUrl: string;
  storageStatePath: string;
  persistentProfilePath: string;
  persistentProfile: boolean;
  headless: boolean;
  diagnose: boolean;
  observationTimeoutMs: number;
  readonlyMode: true;
}

export interface ManualATradObserveOnceSessionLike {
  pages(): ManualATradPageLike[];
  newPage(): Promise<ManualATradPageLike>;
}

export interface ManualATradFrameLike {
  url(): string;
  title(): Promise<string>;
  evaluate<T>(pageFunction: string | (() => T)): Promise<T>;
}

export interface ManualATradPageLike extends ManualATradFrameLike {
  goto(url: string, options: { waitUntil: 'domcontentloaded'; timeout: number }): Promise<void>;
  frames(): ManualATradFrameLike[];
}

export interface ManualATradObserveOnceSessionResource {
  session: ManualATradObserveOnceSessionLike;
  close(): Promise<void>;
}

export interface ManualATradObserveOnceRuntime {
  storageStateExists(path: string): Promise<boolean>;
  launchSession(config: ManualATradObserveOnceConfig): Promise<ManualATradObserveOnceSessionResource>;
  now(): number;
  log(message: string): void;
}

export interface ManualATradFrameDiagnostics {
  scope: string;
  url: string;
  title: string;
  tableCount: number;
  rowCount: number;
  visibleTextCount: number;
  firstVisibleTextSnippets: string[];
  keywordMatches: string[];
}

export interface ManualATradPageDiagnostics {
  pageUrl: string;
  pageTitle: string;
  frameCount: number;
  iframeCount: number;
  page: ManualATradFrameDiagnostics;
  frames: ManualATradFrameDiagnostics[];
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
  diagnostics?: ManualATradPageDiagnostics;
}

export function createManualATradObserveOnceConfig(args: string[] = []): ManualATradObserveOnceConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    persistentProfilePath: ATRAD_PERSISTENT_PROFILE_PATH,
    persistentProfile: args.includes('--persistent-profile'),
    headless: args.includes('--headless'),
    diagnose: args.includes('--diagnose'),
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
    lastPrice: numericField(row, 'Last'),
    bestBid: numericField(row, 'Bid Price'),
    bestAsk: numericField(row, 'Ask Price'),
    bidDepth: numericField(row, 'Bid Qty'),
    askDepth: numericField(row, 'Ask Qty'),
    volume: numericField(row, 'Volume'),
    totalTurnover: numericField(row, 'Turnover'),
    timestamp,
    source: ATRAD_MARKET_WATCH_SOURCE,
    metadata: {
      companyName: field(row, 'Company Name'),
      high: numericField(row, 'High') ?? field(row, 'High'),
      low: numericField(row, 'Low') ?? field(row, 'Low'),
      vwa: numericField(row, 'VWA') ?? field(row, 'VWA'),
      turnover: numericField(row, 'Turnover') ?? field(row, 'Turnover'),
      trades: numericField(row, 'Trades') ?? field(row, 'Trades'),
      priceClose: numericField(row, 'Price Close') ?? field(row, 'Price Close'),
      buySentiment: field(row, 'Buy Sentiment'),
      time: field(row, 'Time'),
      lastQty: numericField(row, 'Last Qty') ?? field(row, 'Last Qty'),
      change: numericField(row, 'Change') ?? field(row, 'Change'),
      percentChange: numericField(row, '% Change') ?? field(row, '% Change'),
      rawRow: { ...row }
    }
  };
}

export function buildMarketWatchRowFromCells(headers: string[], cells: string[]): MarketWatchRow {
  const mapped: MarketWatchRow = {};

  headers.forEach((header, index) => {
    const normalizedHeader = normalizeMarketWatchText(header);
    if (!MARKET_WATCH_HEADERS.includes(normalizedHeader)) {
      return;
    }

    const value = normalizeMarketWatchText(cells[index] ?? '');
    if (value.length > 0) {
      mapped[normalizedHeader] = value;
    }
  });

  return mapped;
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

  if (!isSafeStorageStatePath(config.storageStatePath)) {
    throw new Error(`Unsafe storage state path: ${config.storageStatePath}`);
  }

  if (!isSafePersistentProfilePath(config.persistentProfilePath)) {
    throw new Error(`Unsafe persistent profile path: ${config.persistentProfilePath}`);
  }

  assertATradReadOnlySafety('read Market Watch table data');

  if (!config.persistentProfile && !(await runtime.storageStateExists(config.storageStatePath))) {
    const message = `ATrad storage state is missing or expired. Run pnpm atrad:login first. Expected: ${config.storageStatePath}`;
    runtime.log(message);
    return emptyResult(false, message);
  }

  const resource = await runtime.launchSession(config);
  try {
    const page = resource.session.pages()[0] ?? (await resource.session.newPage());
    await page.goto(config.baseUrl, {
      waitUntil: 'domcontentloaded',
      timeout: config.observationTimeoutMs
    });

    const currentUrl = page.url();
    if (isLoginPageUrl(currentUrl)) {
      const message = config.persistentProfile
        ? `Persistent ATrad session not authenticated. Run pnpm atrad:login -- --base-url ${config.baseUrl} --persistent-profile first.`
        : `ATrad storage-state session not authenticated. Run pnpm atrad:login -- --base-url ${config.baseUrl} first.`;
      runtime.log(message);
      return emptyResult(false, message);
    }

    if (config.diagnose) {
      const diagnostics = await collectPageDiagnostics(page);
      const result: ManualATradObserveOnceResult = {
        ok: true,
        message: 'ATrad observe-once read-only diagnostics completed.',
        rawRows: [],
        rawSnapshots: [],
        accepted: [],
        rejected: [],
        diagnostics
      };

      for (const line of formatObserveOnceSummary(result)) {
        runtime.log(line);
      }

      return result;
    }

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
    await resource.close();
  }
}

export async function extractVisibleMarketWatchRows(page: ManualATradPageLike): Promise<MarketWatchRow[]> {
  assertATradReadOnlySafety('read visible Market Watch table rows');

  return page.evaluate<MarketWatchRow[]>(BROWSER_SAFE_MARKET_WATCH_EVALUATION);
}

export function formatObserveOnceSummary(result: ManualATradObserveOnceResult): string[] {
  if (result.diagnostics) {
    return formatDiagnosticsSummary(result.diagnostics);
  }

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

export async function collectPageDiagnostics(
  page: ManualATradPageLike
): Promise<ManualATradPageDiagnostics> {
  assertATradReadOnlySafety('inspect read-only page diagnostics');

  const pageFrames = page.frames();
  const pageUrl = redactDiagnosticUrl(page.url());
  const pageTitle = redactSensitiveText(await safeTitle(page));
  const pageDiagnostics = await collectFrameDiagnostics(page, 'main-page');
  const frameDiagnostics: ManualATradFrameDiagnostics[] = [];

  for (let index = 1; index < pageFrames.length; index += 1) {
    frameDiagnostics.push(await collectFrameDiagnostics(pageFrames[index], `frame-${index}`));
  }

  return {
    pageUrl,
    pageTitle,
    frameCount: pageFrames.length,
    iframeCount: await page.evaluate<number>(BROWSER_SAFE_IFRAME_COUNT_EVALUATION),
    page: pageDiagnostics,
    frames: frameDiagnostics
  };
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

function isLoginPageUrl(url: string): boolean {
  try {
    return new URL(url).pathname.toLowerCase().includes('/login');
  } catch {
    return url.toLowerCase().includes('/login');
  }
}

function field(row: MarketWatchRow, name: string): string | undefined {
  const value = row[name]?.trim();
  return value && value.length > 0 ? value : undefined;
}

function numericField(row: MarketWatchRow, name: string): string | undefined {
  const value = cleanNumericCellValue(row[name]);
  return value && value.length > 0 ? value : undefined;
}

function normalizeMarketWatchText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function cleanNumericCellValue(value: string | undefined): string | undefined {
  if (!value) return undefined;

  const normalized = value
    .replace(/,/g, '')
    .replace(/[▲▼↑↓↗↘➜•●■◆△▽⬆⬇]/g, '')
    .replace(/[^\d+.\-]/g, '')
    .trim();

  if (!/[0-9]/.test(normalized)) {
    return undefined;
  }

  return normalized.replace(/^\+/, '');
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
    launchSession: async (config) => {
      if (config.persistentProfile) {
        const context = await chromium.launchPersistentContext(config.persistentProfilePath, {
          headless: config.headless
        });
        return {
          session: context,
          close: async () => context.close()
        };
      }

      const browser = await chromium.launch({ headless: config.headless });
      const context = await browser.newContext({ storageState: config.storageStatePath });
      return {
        session: context,
        close: async () => browser.close()
      };
    },
    now: () => Date.now(),
    log: (message) => console.log(message)
  };
}

async function collectFrameDiagnostics(
  frame: ManualATradFrameLike,
  scope: string
): Promise<ManualATradFrameDiagnostics> {
  assertATradReadOnlySafety('inspect read-only frame diagnostics');

  const raw = await frame.evaluate<{
    tableCount: number;
    rowCount: number;
    visibleTextCount: number;
    firstVisibleTextSnippets: string[];
    keywordMatches: string[];
  }>(BROWSER_SAFE_DIAGNOSTICS_EVALUATION);

  return {
    scope,
    url: redactDiagnosticUrl(frame.url()),
    title: redactSensitiveText(await safeTitle(frame)),
    tableCount: raw.tableCount,
    rowCount: raw.rowCount,
    visibleTextCount: raw.visibleTextCount,
    firstVisibleTextSnippets: raw.firstVisibleTextSnippets.map(redactSensitiveText),
    keywordMatches: raw.keywordMatches.map(redactSensitiveText)
  };
}

function formatDiagnosticsSummary(diagnostics: ManualATradPageDiagnostics): string[] {
  const lines = [
    'Sentinel-CSE ATrad observe-once read-only diagnostics',
    `Current page URL: ${diagnostics.pageUrl}`,
    `Page title: ${diagnostics.pageTitle || 'n/a'}`,
    `Frames/iframes detected: ${diagnostics.frameCount}`,
    `iframe elements on page: ${diagnostics.iframeCount}`
  ];

  lines.push(...formatFrameDiagnosticsBlock(diagnostics.page));

  for (const frame of diagnostics.frames) {
    lines.push(...formatFrameDiagnosticsBlock(frame));
  }

  return lines;
}

function formatFrameDiagnosticsBlock(frame: ManualATradFrameDiagnostics): string[] {
  return [
    `${frame.scope}:`,
    `  URL: ${frame.url}`,
    `  Title: ${frame.title || 'n/a'}`,
    `  table elements: ${frame.tableCount}`,
    `  tr elements: ${frame.rowCount}`,
    `  visible text snippets: ${frame.visibleTextCount}`,
    `  first ${DIAGNOSTIC_VISIBLE_TEXT_LIMIT} short visible text snippets: ${
      frame.firstVisibleTextSnippets.length > 0
        ? frame.firstVisibleTextSnippets.join(' | ')
        : 'none'
    }`,
    `  keyword matches: ${frame.keywordMatches.length > 0 ? frame.keywordMatches.join(' | ') : 'none'}`
  ];
}

async function safeTitle(frame: ManualATradFrameLike): Promise<string> {
  try {
    return await frame.title();
  } catch {
    return '';
  }
}

function redactDiagnosticUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return redactSensitiveText(value);
  }
}

function redactSensitiveText(value: string): string {
  return value
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted-email]')
    .replace(/\b(session|token|auth|sid)=([^&\s]+)/gi, '$1=[redacted]')
    .replace(/\b[a-f0-9]{16,}\b/gi, '[redacted-token]')
    .replace(/\b\d{6,}\b/g, '[redacted-number]')
    .trim();
}

const BROWSER_SAFE_MARKET_WATCH_EVALUATION = `(() => {
  const allowedHeaders = ${JSON.stringify(MARKET_WATCH_HEADERS)};
  const preferredKeywords = ${JSON.stringify(PREFERRED_MARKET_WATCH_KEYWORDS)};

  function normalize(value) {
    return String(value || '').replace(/\\s+/g, ' ').trim();
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  function scoreTable(table) {
    const rows = Array.from(table.querySelectorAll('tr')).filter(isVisible);
    if (rows.length < 2) {
      return null;
    }

    let bestHeaderIndex = -1;
    let bestHeaders = [];
    let bestHeaderScore = 0;

    for (let index = 0; index < Math.min(rows.length, 5); index += 1) {
      const candidateHeaders = Array.from(rows[index].querySelectorAll('th,td')).map((cell) =>
        normalize(cell.textContent)
      );
      const headerScore = candidateHeaders.filter((header) => allowedHeaders.includes(header)).length;
      if (headerScore > bestHeaderScore) {
        bestHeaderIndex = index;
        bestHeaders = candidateHeaders;
        bestHeaderScore = headerScore;
      }
    }

    if (
      bestHeaderIndex < 0 ||
      !bestHeaders.includes('Security') ||
      !bestHeaders.includes('Bid Qty') ||
      !bestHeaders.includes('Bid Price') ||
      !bestHeaders.includes('Ask Price') ||
      !bestHeaders.includes('Ask Qty') ||
      !bestHeaders.includes('Last')
    ) {
      return null;
    }

    const container = table.closest('section,article,div') || table.parentElement || table;
    const containerText = normalize(container ? container.textContent : table.textContent);
    const keywordScore = preferredKeywords.filter((keyword) =>
      containerText.toLowerCase().includes(keyword.toLowerCase())
    ).length;

    return {
      rows,
      headerIndex: bestHeaderIndex,
      headers: bestHeaders,
      score: bestHeaderScore * 10 + keywordScore
    };
  }

  const tables = Array.from(document.querySelectorAll('table')).filter(isVisible);
  const scoredTables = tables
    .map((table) => scoreTable(table))
    .filter(Boolean)
    .sort((left, right) => right.score - left.score);

  if (scoredTables.length > 0) {
    const best = scoredTables[0];
    return best.rows
      .slice(best.headerIndex + 1)
      .map((row) => {
        const cells = Array.from(row.querySelectorAll('td,th')).map((cell) => normalize(cell.textContent));
        const mapped = {};
        best.headers.forEach((header, index) => {
          if (allowedHeaders.includes(header)) {
            mapped[header] = normalize(cells[index] || '');
          }
        });
        return mapped;
      })
      .filter((row) =>
        ['Security', 'Company Name', 'Last', 'Volume'].some((header) =>
          Object.prototype.hasOwnProperty.call(row, header) && String(row[header]).length > 0
        )
      );
  }

  return [];
})()`;

const BROWSER_SAFE_IFRAME_COUNT_EVALUATION = `(() => document.querySelectorAll('iframe').length)()`;

const BROWSER_SAFE_DIAGNOSTICS_EVALUATION = `(() => {
  const keywords = ${JSON.stringify(DIAGNOSTIC_KEYWORDS)};
  const maxShortSnippets = ${DIAGNOSTIC_VISIBLE_TEXT_LIMIT};

  function normalize(value) {
    return String(value || '').replace(/\\s+/g, ' ').trim();
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  function collectSnippets() {
    const snippets = [];
    const seen = new Set();
    const root = document.body || document.documentElement;
    const elements = Array.from(root.querySelectorAll('*'));

    for (const element of elements) {
      if (!isVisible(element)) {
        continue;
      }

      const text = normalize(element.textContent);
      if (!text || text.length > 120) {
        continue;
      }

      if (!seen.has(text)) {
        seen.add(text);
        snippets.push(text);
      }
    }

    return snippets;
  }

  const visibleSnippets = collectSnippets();
  const keywordMatches = visibleSnippets.filter((snippet) =>
    keywords.some((keyword) => snippet.toLowerCase().includes(keyword.toLowerCase()))
  );

  return {
    tableCount: document.querySelectorAll('table').length,
    rowCount: document.querySelectorAll('tr').length,
    visibleTextCount: visibleSnippets.length,
    firstVisibleTextSnippets: visibleSnippets.slice(0, maxShortSnippets),
    keywordMatches
  };
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
