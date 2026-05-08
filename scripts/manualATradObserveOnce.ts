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
const TICKER_PATTERN = /\b[A-Z0-9]{2,12}\.[A-Z]\d{4}\b/;

export type MarketWatchRow = Record<string, string>;

export interface ManualATradObserveOnceConfig {
  baseUrl: string;
  storageStatePath: string;
  persistentProfilePath: string;
  persistentProfile: boolean;
  headless: boolean;
  diagnose: boolean;
  debugRows: boolean;
  rawOutput: boolean;
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
  row: MarketWatchRow;
  rawSnapshot: RawMarketSnapshot;
  snapshot?: MarketSnapshot;
  issues: MarketDataSanitizationIssue[];
}

export type ATradParsedRowQualityStatus =
  | 'HIGH_CONFIDENCE'
  | 'MEDIUM_CONFIDENCE'
  | 'LOW_CONFIDENCE'
  | 'REJECTED';

export type ATradParsedRowQualityIssueCode =
  | 'LAST_OUTSIDE_BID_ASK_RANGE'
  | 'LAST_LOOKS_LIKE_QUANTITY'
  | 'VOLUME_LOOKS_LIKE_PERCENT'
  | 'TURNOVER_LOOKS_LIKE_TIME'
  | 'TRADES_LOOKS_LIKE_PERCENT'
  | 'VWA_OUTSIDE_PRICE_RANGE'
  | 'TRAILING_FIELDS_SHIFTED'
  | 'TIME_FIELD_SHIFTED'
  | 'LOW_MAPPING_CONFIDENCE';

export interface ATradParsedRowQualityIssue {
  code: ATradParsedRowQualityIssueCode;
  message: string;
  field?: string;
}

export interface ATradParsedRowQualityAssessment {
  ticker?: string;
  status: ATradParsedRowQualityStatus;
  issues: ATradParsedRowQualityIssue[];
  sanitizerIssueCodes: string[];
  row: MarketWatchRow;
  rawSnapshot: RawMarketSnapshot;
}

export interface ATradParsedRowQualitySummary {
  highConfidenceCount: number;
  mediumConfidenceCount: number;
  lowConfidenceCount: number;
  rejectedCount: number;
  lowConfidenceRows: ATradParsedRowQualityAssessment[];
}

export interface MarketWatchDebugRowResult {
  cells: string[];
  cellCount: number;
  accepted: boolean;
  reasons: string[];
  parsedRow?: MarketWatchRow;
  sanitizerIssueCodes?: string[];
}

export interface MarketWatchTableCandidateDebug {
  kind: 'table' | 'dojo-grid';
  score: number;
  headerRowIndex: number;
  headerCells: string[];
  sampleRows: string[][];
  containerTextMatches: string[];
  rowAnalyses: MarketWatchDebugRowResult[];
}

export interface DojoGridViewSummary {
  viewIndex: number;
  rowCount: number;
  firstRows: string[][];
}

export interface MarketWatchExtractionDebug {
  candidateCount: number;
  chosenCandidate?: MarketWatchTableCandidateDebug;
  dojoDebug?: {
    gridCount: number;
    viewCount: number;
    viewSummaries: DojoGridViewSummary[];
    sampleRows: string[][];
    parsedRows: MarketWatchRow[];
    rowAnalyses: MarketWatchDebugRowResult[];
  };
  broadScan?: {
    visibleTableCount: number;
    visibleTrCount: number;
    visibleRoleGridCount: number;
    visibleRoleTableCount: number;
    visibleRoleRowCount: number;
    tableSummaries: BroadVisibleTableSummary[];
    gridSummaries: BroadVisibleGridSummary[];
  };
  headerMatches?: HeaderSearchMatch[];
}

export interface BroadVisibleTableSummary {
  index: number;
  nearbyTextSnippet: string;
  rowCount: number;
  firstRows: string[][];
  keywordMatches: string[];
}

export interface BroadVisibleGridSummary {
  index: number;
  typeHint: string;
  nearbyTextSnippet: string;
  childTextChunks: string[];
  keywordMatches: string[];
}

export interface HeaderSearchMatch {
  text: string;
  tagName: string;
  role: string;
  className: string;
  ancestorTextSnippet: string;
  ancestorTagChain: string;
}

export interface ManualATradObserveOnceResult {
  ok: boolean;
  message: string;
  rawRows: MarketWatchRow[];
  rawSnapshots: RawMarketSnapshot[];
  accepted: SanitizedObservedMarketWatchRow[];
  rejected: SanitizedObservedMarketWatchRow[];
  qualityAssessments: ATradParsedRowQualityAssessment[];
  qualitySummary: ATradParsedRowQualitySummary;
  rawOutputEnabled?: boolean;
  diagnostics?: ManualATradPageDiagnostics;
  extractionDebug?: MarketWatchExtractionDebug;
}

export function createManualATradObserveOnceConfig(args: string[] = []): ManualATradObserveOnceConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    persistentProfilePath: ATRAD_PERSISTENT_PROFILE_PATH,
    persistentProfile: args.includes('--persistent-profile'),
    headless: args.includes('--headless'),
    diagnose: args.includes('--diagnose'),
    debugRows: args.includes('--debug-rows'),
    rawOutput: args.includes('--raw-output'),
    observationTimeoutMs: parseTimeoutMs(args),
    readonlyMode: true
  };
}

export function marketWatchRowToRawSnapshot(
  row: MarketWatchRow,
  timestamp: number
): RawMarketSnapshot {
  const ticker = extractCseTicker(field(row, 'Security')) ?? field(row, 'Security');
  return {
    ticker,
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
      mapped[normalizedHeader] = normalizedHeader === 'Security'
        ? extractCseTicker(value) ?? value
        : value;
    }
  });

  return mapped;
}

export function normalizeATradFullWatchEquityRow(cells: string[]): MarketWatchRow {
  const normalizedCells = cells
    .map((cell) => normalizeMarketWatchText(cell))
    .filter((cell) => cell.length > 0);
  const tickerIndex = normalizedCells.findIndex((cell) => Boolean(extractCseTicker(cell)));

  if (tickerIndex < 0) {
    return {};
  }

  const working = normalizedCells.slice(tickerIndex);
  if (working.length < 14) {
    return {};
  }

  const mapped: MarketWatchRow = {};
  const ticker = extractCseTicker(working[0]);
  if (ticker) {
    mapped.Security = ticker;
  }

  let cursor = 1;
  if (isLikelyCompanyName(working[cursor])) {
    mapped['Company Name'] = working[cursor] as string;
    cursor += 1;
  }

  const leadingHeaders = ['Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty'] as const;
  for (const header of leadingHeaders) {
    const value = working[cursor];
    if (value) {
      mapped[header] = value;
      cursor += 1;
    }
  }

  const bid = parseNumericValue(mapped['Bid Price']);
  const ask = parseNumericValue(mapped['Ask Price']);
  const trailing = working.slice(cursor);
  let end = trailing.length - 1;

  const tryPop = (predicate: (value: string, endIndex: number) => boolean): string | undefined => {
    const value = trailing[end];
    if (value && predicate(value, end)) {
      end -= 1;
      return value;
    }

    return undefined;
  };

  const time = tryPop((value) => isLikelyTimeValue(value));
  if (time) {
    mapped.Time = time;
  }

  const buySentiment = tryPop((value) => isPercentValue(value));
  if (buySentiment) {
    mapped['Buy Sentiment'] = buySentiment;
  }

  const priceClose = tryPop((value, endIndex) => endIndex >= 5 && isNumericLike(value));
  if (priceClose) {
    mapped['Price Close'] = priceClose;
  }

  const trades = tryPop(
    (value, endIndex) => endIndex >= 6 && isIntegerLike(value) && !value.includes(',')
  );
  if (trades) {
    mapped.Trades = trades;
  }

  const turnover = tryPop((value, endIndex) => endIndex >= 5 && isLikelyTurnoverValue(value));
  if (turnover) {
    mapped.Turnover = turnover;
  }

  const volume = tryPop((value, endIndex) => endIndex >= 4 && isLikelyVolumeValue(value, bid, ask));
  if (volume) {
    mapped.Volume = volume;
  }

  const vwa = tryPop((value, endIndex) => endIndex >= 5 && isPriceLikeNearReference(value, bid, ask));
  if (vwa) {
    mapped.VWA = vwa;
  }

  const middle = trailing.slice(0, end + 1);
  const lastIndex = findLikelyLastIndex(middle, bid, ask);

  if (lastIndex >= 0) {
    mapped.Last = middle[lastIndex] as string;
  }

  const afterLast = lastIndex >= 0 ? middle.slice(lastIndex + 1) : middle;
  let middleCursor = 0;

  if (isLikelyLastQuantityValue(afterLast[middleCursor], bid, ask)) {
    mapped['Last Qty'] = afterLast[middleCursor] as string;
    middleCursor += 1;
  }

  if (isLikelyChangeValue(afterLast[middleCursor], bid, ask, mapped.Last)) {
    mapped.Change = afterLast[middleCursor] as string;
    middleCursor += 1;
  }

  if (isLikelyPercentChangeValue(afterLast[middleCursor])) {
    mapped['% Change'] = afterLast[middleCursor] as string;
    middleCursor += 1;
  }

  const remainingPriceCandidates = afterLast
    .slice(middleCursor)
    .filter((value) => isPriceLikeNearReference(value, bid, ask, parseNumericValue(mapped.Last)));

  if (remainingPriceCandidates.length >= 1) {
    mapped.High = remainingPriceCandidates[0] as string;
  }
  if (remainingPriceCandidates.length >= 3) {
    mapped.Low = remainingPriceCandidates[1] as string;
    const vwaCandidate = remainingPriceCandidates[2] as string;
    if (looksLikeVwaCandidate(vwaCandidate, bid, ask, parseNumericValue(mapped.Last))) {
      mapped.VWA = mapped.VWA ?? vwaCandidate;
    }
  } else if (remainingPriceCandidates.length === 2) {
    const secondCandidate = remainingPriceCandidates[1] as string;
    const minReference = Math.min(...[bid, ask, parseNumericValue(mapped.Last)].filter((entry): entry is number => entry !== undefined));
    const maxReference = Math.max(...[bid, ask, parseNumericValue(mapped.Last)].filter((entry): entry is number => entry !== undefined));
    if (
      Number.isFinite(minReference) &&
      Number.isFinite(maxReference) &&
      parseNumericValue(secondCandidate) !== undefined &&
      parseNumericValue(secondCandidate)! >= minReference &&
      parseNumericValue(secondCandidate)! <= maxReference &&
      looksLikeVwaCandidate(secondCandidate, bid, ask, parseNumericValue(mapped.Last))
    ) {
      mapped.VWA = mapped.VWA ?? secondCandidate;
    } else {
      mapped.Low = secondCandidate;
    }
  }

  return cleanupATradParsedRow(mapped);
}

export function parseDojoWatchGridRow(headers: string[], cells: string[]): MarketWatchRow {
  let mapped = cleanupATradParsedRow(buildMarketWatchRowFromCells(headers, cells));
  const normalizedHeaders = headers.map((header) => normalizeMarketWatchText(header));
  const securityHeaderIndex = normalizedHeaders.findIndex((header) => header === 'Security');
  const tickerIndex = cells.findIndex((cell) => Boolean(extractCseTicker(cell)));

  if (securityHeaderIndex >= 0 && tickerIndex >= 0 && tickerIndex !== securityHeaderIndex) {
    const offsetMapped: MarketWatchRow = {};
    normalizedHeaders.forEach((header, index) => {
      if (!MARKET_WATCH_HEADERS.includes(header)) {
        return;
      }

      const value = normalizeMarketWatchText(cells[index + (tickerIndex - securityHeaderIndex)] ?? '');
      if (value.length > 0) {
        offsetMapped[header] = value;
      }
    });

    if (Object.keys(offsetMapped).length > Object.keys(mapped).length) {
      mapped = cleanupATradParsedRow(offsetMapped);
    }
  }

  const normalizedFullWatch = normalizeATradFullWatchEquityRow(cells);
  if (Object.keys(normalizedFullWatch).length > 0) {
    const merged = cleanupATradParsedRow({ ...mapped, ...normalizedFullWatch });
    if (scoreMarketWatchRow(merged) >= scoreMarketWatchRow(mapped)) {
      mapped = merged;
    }
  }

  if (!mapped.Security) {
    const tickerText = cells.find((cell) => Boolean(extractCseTicker(cell))) ?? '';
    const ticker = extractCseTicker(tickerText);
    if (ticker) {
      mapped.Security = ticker;
    }
  }

  return cleanupATradParsedRow(mapped);
}

function scoreMarketWatchRow(row: MarketWatchRow): number {
  return MARKET_WATCH_HEADERS.reduce((score, header) => {
    if (!field(row, header)) {
      return score;
    }

    return score + (numericField(row, header) ? 2 : 1);
  }, 0);
}

function dedupeDojoMarketWatchRows(rows: MarketWatchRow[]): MarketWatchRow[] {
  const deduped = new Map<string, MarketWatchRow>();

  for (const row of rows) {
    const ticker = field(row, 'Security');
    const key = ticker ?? JSON.stringify(row);
    const existing = deduped.get(key);

    if (!existing || scoreMarketWatchRow(row) > scoreMarketWatchRow(existing)) {
      deduped.set(key, row);
    }
  }

  return Array.from(deduped.values());
}

export function assessATradParsedSnapshotQuality(
  row: MarketWatchRow,
  rawSnapshot: RawMarketSnapshot,
  sanitizedResult: { accepted: boolean; issues: Array<{ code: string }> }
): ATradParsedRowQualityAssessment {
  const issues: ATradParsedRowQualityIssue[] = [];
  const bid = parseNumericValue(row['Bid Price']);
  const ask = parseNumericValue(row['Ask Price']);
  const last = parseNumericValue(row.Last);
  const vwa = parseNumericValue(row.VWA);

  if (row.Volume && isPercentValue(row.Volume)) {
    issues.push(issue('VOLUME_LOOKS_LIKE_PERCENT', 'Volume looks like a percent field.', 'Volume'));
  }

  if (row.Turnover && isLikelyTimeValue(row.Turnover)) {
    issues.push(issue('TURNOVER_LOOKS_LIKE_TIME', 'Turnover looks like a time value.', 'Turnover'));
  }

  if (row.Trades && isPercentValue(row.Trades)) {
    issues.push(issue('TRADES_LOOKS_LIKE_PERCENT', 'Trades looks like a percent field.', 'Trades'));
  }

  if (row.Time && !isLikelyTimeValue(row.Time)) {
    issues.push(issue('TIME_FIELD_SHIFTED', 'Time field does not look like a time value.', 'Time'));
  }

  const misplacedTimeField = findMisplacedTimeField(row);
  if (!row.Time && misplacedTimeField) {
    issues.push(
      issue(
        'TIME_FIELD_SHIFTED',
        `Time-like value appears in ${misplacedTimeField} instead of Time.`,
        misplacedTimeField
      )
    );
  }

  const misplacedPercentField = findMisplacedPercentField(row);
  if (!row['Buy Sentiment'] && misplacedPercentField) {
    issues.push(
      issue(
        'TRAILING_FIELDS_SHIFTED',
        `Percent-like value appears in ${misplacedPercentField} while Buy Sentiment is missing.`,
        misplacedPercentField
      )
    );
  }

  if (row['Price Close'] && (isPercentValue(row['Price Close']) || isLikelyTimeValue(row['Price Close']))) {
    issues.push(
      issue(
        'TRAILING_FIELDS_SHIFTED',
        'Price Close looks like a shifted percent or time field.',
        'Price Close'
      )
    );
  }

  if (bid !== undefined && ask !== undefined && last !== undefined) {
    const spread = Math.max(ask - bid, 0);
    const tolerance = Math.max(spread * 3, ask * 0.03);
    if (last < bid - tolerance || last > ask + tolerance) {
      issues.push(
        issue(
          'LAST_OUTSIDE_BID_ASK_RANGE',
          'Last price sits far outside the current bid/ask range.',
          'Last'
        )
      );
    }

    if (
      isIntegerLike(row.Last) &&
      (String(row['Bid Price'] ?? '').includes('.') || String(row['Ask Price'] ?? '').includes('.')) &&
      last > ask * 3
    ) {
      issues.push(
        issue(
          'LAST_LOOKS_LIKE_QUANTITY',
          'Last looks more like a quantity than a tradable price.',
          'Last'
        )
      );
    }
  }

  if (
    vwa !== undefined &&
    bid !== undefined &&
    ask !== undefined &&
    last !== undefined
  ) {
    const referenceHigh = Math.max(bid, ask, last);
    const referenceLow = Math.min(bid, ask, last);
    if (vwa > referenceHigh * 5 || vwa < referenceLow / 5) {
      issues.push(
        issue(
          'VWA_OUTSIDE_PRICE_RANGE',
          'VWA looks far outside the observed price range.',
          'VWA'
        )
      );
    }
  }

  if (sanitizedResult.accepted && issues.length === 0) {
    const mappedCoreFields = ['Security', 'Bid Price', 'Ask Price', 'Last', 'Volume'].filter((fieldName) =>
      field(row, fieldName)
    ).length;
    if (mappedCoreFields < 5) {
      issues.push(
        issue(
          'LOW_MAPPING_CONFIDENCE',
          'Required trading fields are present but the core mapping confidence is low.'
        )
      );
    }
  }

  const sanitizerIssueCodes = sanitizedResult.issues.map((entry) => entry.code);
  const dedupedIssues = dedupeQualityIssues(issues);

  return {
    ticker: field(row, 'Security'),
    status: determineQualityStatus(dedupedIssues, sanitizedResult.accepted),
    issues: dedupedIssues,
    sanitizerIssueCodes,
    row,
    rawSnapshot
  };
}

export function buildATradParsedRowQualitySummary(
  assessments: ATradParsedRowQualityAssessment[]
): ATradParsedRowQualitySummary {
  return {
    highConfidenceCount: assessments.filter((assessment) => assessment.status === 'HIGH_CONFIDENCE').length,
    mediumConfidenceCount: assessments.filter((assessment) => assessment.status === 'MEDIUM_CONFIDENCE').length,
    lowConfidenceCount: assessments.filter((assessment) => assessment.status === 'LOW_CONFIDENCE').length,
    rejectedCount: assessments.filter((assessment) => assessment.status === 'REJECTED').length,
    lowConfidenceRows: assessments
      .filter((assessment) => assessment.status === 'LOW_CONFIDENCE')
      .slice(0, 5)
  };
}

export function sanitizeMarketWatchRows(
  rows: MarketWatchRow[],
  timestamp: number,
  sanitizer: MarketDataSanitizer = new MarketDataSanitizer({ source: ATRAD_MARKET_WATCH_SOURCE })
): Pick<ManualATradObserveOnceResult, 'rawSnapshots' | 'accepted' | 'rejected' | 'qualityAssessments' | 'qualitySummary'> {
  const rawSnapshots = rows.map((row) => marketWatchRowToRawSnapshot(row, timestamp));
  const accepted: SanitizedObservedMarketWatchRow[] = [];
  const rejected: SanitizedObservedMarketWatchRow[] = [];
  const qualityAssessments: ATradParsedRowQualityAssessment[] = [];

  for (const [index, rawSnapshot] of rawSnapshots.entries()) {
    const row = rows[index] ?? {};
    const result = sanitizer.sanitize(rawSnapshot);
    const rowResult: SanitizedObservedMarketWatchRow = {
      row,
      rawSnapshot,
      snapshot: result.snapshot,
      issues: result.issues
    };
    qualityAssessments.push(assessATradParsedSnapshotQuality(row, rawSnapshot, result));

    if (result.accepted) {
      accepted.push(rowResult);
    } else {
      rejected.push(rowResult);
    }
  }

  return {
    rawSnapshots,
    accepted,
    rejected,
    qualityAssessments,
    qualitySummary: buildATradParsedRowQualitySummary(qualityAssessments)
  };
}

export function analyzeMarketWatchRows(
  kind: 'table' | 'dojo-grid',
  headers: string[],
  rows: string[][],
  timestamp: number,
  sanitizer: MarketDataSanitizer = new MarketDataSanitizer({ source: ATRAD_MARKET_WATCH_SOURCE })
): MarketWatchDebugRowResult[] {
  return rows.slice(0, 10).map((cells) => {
    const reasons: string[] = [];
    const parsedRow = parseMarketWatchCandidateRow(kind, headers, cells);
    const minimumCellCount = kind === 'dojo-grid' ? 7 : Math.max(headers.length - 1, 4);

    if (cells.length < minimumCellCount) {
      reasons.push('not enough cells');
    }

    if (!field(parsedRow, 'Security')) {
      reasons.push('missing ticker');
    }

    if (field(parsedRow, 'Security') && !numericField(parsedRow, 'Last') && !numericField(parsedRow, 'Bid Price') && !numericField(parsedRow, 'Ask Price')) {
      reasons.push('ticker only');
    }

    if (!numericField(parsedRow, 'Last')) {
      reasons.push('missing last price');
    }

    if (!numericField(parsedRow, 'Bid Price') || !numericField(parsedRow, 'Ask Price')) {
      reasons.push('missing bid/ask');
    }

    if (field(parsedRow, 'Security') && !numericField(parsedRow, 'Volume') && !numericField(parsedRow, 'Turnover') && !numericField(parsedRow, 'Last')) {
      reasons.push('unable to map numeric columns');
    }

    const rowText = cells.join(' ').toLowerCase();
    const looksLikeHeaderOrSummary =
      cells.every((cell) => normalizeMarketWatchText(cell).length === 0) ||
      rowText.includes('security') ||
      rowText.includes('total') ||
      rowText.includes('summary');
    if (looksLikeHeaderOrSummary) {
      reasons.push('row looked like header/summary');
    }

    const sanitizerIssueCodes: string[] = [];
    if (reasons.length === 0) {
      const result = sanitizer.sanitize(marketWatchRowToRawSnapshot(parsedRow, timestamp));
      if (!result.accepted) {
        sanitizerIssueCodes.push(...result.issues.map((issue) => issue.code));
        reasons.push(`sanitizer rejected: ${sanitizerIssueCodes.join(', ')}`);
      }
    }

    return {
      cells,
      cellCount: cells.length,
      accepted: reasons.length === 0,
      reasons,
      parsedRow: Object.keys(parsedRow).length > 0 ? parsedRow : undefined,
      sanitizerIssueCodes: sanitizerIssueCodes.length > 0 ? sanitizerIssueCodes : undefined
    };
  });
}

function parseMarketWatchCandidateRow(
  kind: 'table' | 'dojo-grid',
  headers: string[],
  cells: string[]
): MarketWatchRow {
  return kind === 'dojo-grid'
    ? parseDojoWatchGridRow(headers, cells)
    : buildMarketWatchRowFromCells(headers, cells);
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
        qualityAssessments: [],
        qualitySummary: emptyQualitySummary(),
        diagnostics
      };

      for (const line of formatObserveOnceSummary(result)) {
        runtime.log(line);
      }

      return result;
    }

    if (config.debugRows) {
      const result = await debugMarketWatchRows(page, runtime.now());
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
      rawOutputEnabled: config.rawOutput,
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

  const extraction = await extractMarketWatchTableCandidates(page);
  const chosen = extraction.candidates[extraction.chosenCandidateIndex];
  if (!chosen) {
    return [];
  }

  const parsedRows = chosen.rows
    .map((cells) => parseMarketWatchCandidateRow(chosen.kind, chosen.headerCells, cells))
    .filter((row) =>
      ['Security', 'Company Name', 'Last', 'Volume'].some((header) =>
        Object.prototype.hasOwnProperty.call(row, header) && String(row[header]).length > 0
      )
    );

  return chosen.kind === 'dojo-grid'
    ? dedupeDojoMarketWatchRows(parsedRows)
    : parsedRows;
}

export function formatObserveOnceSummary(result: ManualATradObserveOnceResult): string[] {
  if (result.diagnostics) {
    return formatDiagnosticsSummary(result.diagnostics);
  }

  if (result.extractionDebug) {
    return formatExtractionDebugSummary(result.extractionDebug);
  }

  const lines = [
    'Sentinel-CSE ATrad observe-once read-only summary',
    `Raw rows extracted: ${result.rawRows.length}`,
    `Accepted snapshots: ${result.accepted.length}`,
    `Rejected snapshots: ${result.rejected.length}`,
    'Quality summary:',
    `- high confidence: ${result.qualitySummary.highConfidenceCount}`,
    `- medium confidence: ${result.qualitySummary.mediumConfidenceCount}`,
    `- low confidence: ${result.qualitySummary.lowConfidenceCount}`,
    `- rejected: ${result.qualitySummary.rejectedCount}`,
    ...result.qualitySummary.lowConfidenceRows.flatMap((assessment, index) => [
      `Low-confidence row ${index + 1}: ${assessment.ticker ?? 'unknown'} [${assessment.status}]`,
      `- ${assessment.issues.map((issue) => issue.code).join(', ')}`
    ]),
    ...result.rejected.flatMap((row, index) => [
      `Rejected row ${index + 1}: ${String(row.rawSnapshot.ticker ?? 'unknown')}`,
      ...row.issues.map((issue) => `- ${issue.code}: ${issue.message}`)
    ])
  ];

  if (result.rawOutputEnabled) {
    lines.splice(2, 0, JSON.stringify(result.rawRows, null, 2));
  }

  return lines;
}

export async function debugMarketWatchRows(
  page: ManualATradPageLike,
  timestamp: number
): Promise<ManualATradObserveOnceResult> {
  assertATradReadOnlySafety('inspect read-only market watch row extraction debug');

  const extraction = await extractMarketWatchTableCandidates(page);
  const chosen = extraction.candidates[extraction.chosenCandidateIndex];
  const dojoCandidates = extraction.dojoCandidates ?? [];

  return {
    ok: true,
    message: 'ATrad observe-once read-only row debug completed.',
    rawRows: [],
    rawSnapshots: [],
    accepted: [],
    rejected: [],
    qualityAssessments: [],
    qualitySummary: emptyQualitySummary(),
    extractionDebug: {
      candidateCount: extraction.candidates.length,
      chosenCandidate: chosen
        ? {
            kind: chosen.kind,
            score: chosen.score,
            headerRowIndex: chosen.headerRowIndex,
            headerCells: chosen.headerCells,
            sampleRows: chosen.rows.slice(0, 10),
            containerTextMatches: chosen.containerTextMatches,
            rowAnalyses: analyzeMarketWatchRows(chosen.kind, chosen.headerCells, chosen.rows, timestamp)
          }
        : undefined,
      dojoDebug: dojoCandidates.length > 0
        ? {
            gridCount: dojoCandidates.length,
            viewCount: dojoCandidates[0]?.viewCount ?? 0,
            viewSummaries: dojoCandidates[0]?.viewSummaries ?? [],
            sampleRows: dojoCandidates[0]?.rows.slice(0, 10) ?? [],
            parsedRows: (dojoCandidates[0]?.rows ?? []).slice(0, 10).map((cells) =>
              parseMarketWatchCandidateRow('dojo-grid', dojoCandidates[0]?.headerCells ?? [], cells)
            ),
            rowAnalyses: analyzeMarketWatchRows(
              'dojo-grid',
              dojoCandidates[0]?.headerCells ?? [],
              dojoCandidates[0]?.rows ?? [],
              timestamp
            )
          }
        : undefined,
      broadScan: extraction.broadScan,
      headerMatches: extraction.headerMatches
    }
  };
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

function issue(
  code: ATradParsedRowQualityIssueCode,
  message: string,
  field?: string
): ATradParsedRowQualityIssue {
  return { code, message, field };
}

function determineQualityStatus(
  issues: ATradParsedRowQualityIssue[],
  sanitizerAccepted: boolean
): ATradParsedRowQualityStatus {
  if (!sanitizerAccepted) {
    return 'REJECTED';
  }

  if (issues.length === 0) {
    return 'HIGH_CONFIDENCE';
  }

  const lowConfidenceCodes: ATradParsedRowQualityIssueCode[] = [
    'LAST_OUTSIDE_BID_ASK_RANGE',
    'LAST_LOOKS_LIKE_QUANTITY',
    'VOLUME_LOOKS_LIKE_PERCENT',
    'LOW_MAPPING_CONFIDENCE'
  ];

  return issues.some((entry) => lowConfidenceCodes.includes(entry.code))
    ? 'LOW_CONFIDENCE'
    : 'MEDIUM_CONFIDENCE';
}

function dedupeQualityIssues(issues: ATradParsedRowQualityIssue[]): ATradParsedRowQualityIssue[] {
  const seen = new Set<string>();
  return issues.filter((entry) => {
    const key = `${entry.code}:${entry.field ?? ''}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function findMisplacedPercentField(row: MarketWatchRow): string | undefined {
  const candidateFields = ['Last Qty', 'High', 'Low', 'VWA', 'Volume', 'Turnover', 'Trades', 'Price Close'];
  return candidateFields.find((fieldName) => isPercentValue(row[fieldName]));
}

function findMisplacedTimeField(row: MarketWatchRow): string | undefined {
  const candidateFields = ['Turnover', 'Trades', 'Price Close', 'Buy Sentiment', 'VWA', 'Volume'];
  return candidateFields.find((fieldName) => isLikelyTimeValue(row[fieldName]));
}

function parseNumericValue(value: string | undefined): number | undefined {
  const normalized = cleanNumericCellValue(value);
  if (!normalized) {
    return undefined;
  }

  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function emptyQualitySummary(): ATradParsedRowQualitySummary {
  return {
    highConfidenceCount: 0,
    mediumConfidenceCount: 0,
    lowConfidenceCount: 0,
    rejectedCount: 0,
    lowConfidenceRows: []
  };
}

function cleanupATradParsedRow(row: MarketWatchRow): MarketWatchRow {
  const cleaned: MarketWatchRow = { ...row };
  const bid = parseNumericValue(cleaned['Bid Price']);
  const ask = parseNumericValue(cleaned['Ask Price']);
  const last = parseNumericValue(cleaned.Last);

  movePercentFieldToBuySentiment(cleaned, 'Trades');
  movePercentFieldToBuySentiment(cleaned, 'Price Close');
  movePercentFieldToBuySentiment(cleaned, 'Turnover');
  movePercentFieldToBuySentiment(cleaned, 'Volume');
  movePercentFieldToBuySentiment(cleaned, 'VWA');

  moveTimeFieldToTime(cleaned, 'Turnover');
  moveTimeFieldToTime(cleaned, 'Trades');
  moveTimeFieldToTime(cleaned, 'Price Close');
  moveTimeFieldToTime(cleaned, 'Buy Sentiment');
  moveTimeFieldToTime(cleaned, 'VWA');
  moveTimeFieldToTime(cleaned, 'Volume');

  if (cleaned.Trades && (!isIntegerLike(cleaned.Trades) || isPercentValue(cleaned.Trades))) {
    delete cleaned.Trades;
  }

  if (
    cleaned['Price Close'] &&
    (!isPriceLikeNearReference(cleaned['Price Close'], bid, ask, last) ||
      isPercentValue(cleaned['Price Close']) ||
      isLikelyTimeValue(cleaned['Price Close']))
  ) {
    delete cleaned['Price Close'];
  }

  if (
    cleaned.VWA &&
    !looksLikeVwaCandidate(cleaned.VWA, bid, ask, last)
  ) {
    delete cleaned.VWA;
  }

  if (cleaned['Buy Sentiment'] && !isPercentValue(cleaned['Buy Sentiment'])) {
    delete cleaned['Buy Sentiment'];
  }

  if (cleaned.Time && !isLikelyTimeValue(cleaned.Time)) {
    delete cleaned.Time;
  }

  const ticker = extractCseTicker(cleaned.Security);
  if (ticker) {
    cleaned.Security = ticker;
  }

  return cleaned;
}

function movePercentFieldToBuySentiment(row: MarketWatchRow, fieldName: string): void {
  const value = row[fieldName];
  if (value && isPercentValue(value) && !row['Buy Sentiment']) {
    row['Buy Sentiment'] = value;
    delete row[fieldName];
  }
}

function moveTimeFieldToTime(row: MarketWatchRow, fieldName: string): void {
  const value = row[fieldName];
  if (value && isLikelyTimeValue(value) && !row.Time) {
    row.Time = value;
    delete row[fieldName];
  }
}

function extractCseTicker(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }

  const normalized = normalizeMarketWatchText(value).toUpperCase();
  const match = normalized.match(/[A-Z0-9]{2,12}\.[A-Z]\d{4}/);
  return match?.[0];
}

function isLikelyCompanyName(value: string | undefined): boolean {
  if (!value) {
    return false;
  }

  return !extractCseTicker(value) && !isPercentValue(value) && !isLikelyTimeValue(value) && !isNumericLike(value);
}

function findLikelyLastIndex(
  values: string[],
  bid: number | undefined,
  ask: number | undefined
): number {
  let bestIndex = -1;
  let bestScore = Number.NEGATIVE_INFINITY;

  values.forEach((value, index) => {
    const score = scoreLikelyLastValue(value, index, bid, ask);
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  });

  return bestScore > 0 ? bestIndex : -1;
}

function scoreLikelyLastValue(
  value: string | undefined,
  index: number,
  bid: number | undefined,
  ask: number | undefined
): number {
  if (!value || isPercentValue(value) || isLikelyTimeValue(value)) {
    return Number.NEGATIVE_INFINITY;
  }

  const numeric = parseNumericValue(value);
  if (numeric === undefined) {
    return Number.NEGATIVE_INFINITY;
  }

  let score = 30 - index * 4;
  const hasDecimalInMarket = String(bid ?? '').includes('.') || String(ask ?? '').includes('.');
  if (hasDecimalInMarket && value.includes('.')) {
    score += 10;
  }

  if (bid !== undefined && ask !== undefined) {
    const midpoint = (bid + ask) / 2;
    const spread = Math.max(Math.abs(ask - bid), midpoint * 0.0025);
    const distance = Math.abs(numeric - midpoint);
    if (distance <= Math.max(spread * 4, midpoint * 0.03)) {
      score += 50;
    } else if (distance <= Math.max(spread * 15, midpoint * 0.12)) {
      score += 20;
    } else {
      score -= 40;
    }

    if (numeric > Math.max(bid, ask) * 3 || numeric < Math.min(bid, ask) / 3) {
      score -= 30;
    }

    if (isLikelyQuantityValue(value, bid, ask)) {
      score -= 35;
    }
  }

  return score;
}

function isPriceLikeNearReference(
  value: string | undefined,
  ...references: Array<number | undefined>
): boolean {
  const numeric = parseNumericValue(value);
  if (numeric === undefined || isPercentValue(value) || isLikelyTimeValue(value)) {
    return false;
  }

  const filteredReferences = references.filter((entry): entry is number => entry !== undefined);
  if (filteredReferences.length === 0) {
    return numeric < 10_000;
  }

  const referenceHigh = Math.max(...filteredReferences);
  const referenceLow = Math.min(...filteredReferences);
  return numeric >= referenceLow / 2 && numeric <= referenceHigh * 2;
}

function isLikelyQuantityValue(
  value: string | undefined,
  bid: number | undefined,
  ask: number | undefined
): boolean {
  const numeric = parseNumericValue(value);
  if (numeric === undefined || isPercentValue(value) || isLikelyTimeValue(value)) {
    return false;
  }

  const reference = Math.max(bid ?? 0, ask ?? 0);
  return isIntegerLike(value) && (value.includes(',') || (reference > 0 && numeric > reference * 3) || numeric >= 1000);
}

function isLikelyLastQuantityValue(
  value: string | undefined,
  bid: number | undefined,
  ask: number | undefined
): boolean {
  return (
    !!value &&
    isIntegerLike(value) &&
    !isPercentValue(value) &&
    !isLikelyTimeValue(value) &&
    !isPriceLikeNearReference(value, bid, ask)
  );
}

function isLikelyChangeValue(
  value: string | undefined,
  bid: number | undefined,
  ask: number | undefined,
  last: string | undefined
): boolean {
  const numeric = parseNumericValue(value);
  if (numeric === undefined || isPercentValue(value) || isLikelyTimeValue(value)) {
    return false;
  }

  const reference = Math.max(parseNumericValue(last) ?? 0, bid ?? 0, ask ?? 0, 1);
  return Math.abs(numeric) <= Math.max(reference * 0.2, 20);
}

function isLikelyPercentChangeValue(value: string | undefined): boolean {
  if (isPercentValue(value)) {
    return true;
  }

  const numeric = parseNumericValue(value);
  return numeric !== undefined && Math.abs(numeric) <= 25;
}

function looksLikeVwaCandidate(
  value: string | undefined,
  bid: number | undefined,
  ask: number | undefined,
  last: number | undefined
): boolean {
  const numeric = parseNumericValue(value);
  if (numeric === undefined) {
    return false;
  }

  const references = [bid, ask, last].filter((entry): entry is number => entry !== undefined);
  if (references.length === 0) {
    return false;
  }

  const high = Math.max(...references);
  const low = Math.min(...references);
  return numeric >= low * 0.98 && numeric <= high * 1.02;
}

function isLikelyTimeValue(value: string | undefined): boolean {
  return typeof value === 'string' && /^\d{1,2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value.trim());
}

function isPercentValue(value: string | undefined): boolean {
  return typeof value === 'string' && /^[+-]?\d[\d,]*\.?\d*%$/.test(value.trim());
}

function isNumericLike(value: string | undefined): boolean {
  return typeof cleanNumericCellValue(value) === 'string';
}

function isIntegerLike(value: string | undefined): boolean {
  const normalized = cleanNumericCellValue(value);
  return typeof normalized === 'string' && !normalized.includes('.');
}

function isLikelyTurnoverValue(value: string | undefined): boolean {
  const numeric = parseNumericValue(value);
  return typeof value === 'string' && numeric !== undefined && value.includes('.') && numeric >= 1_000;
}

function isLikelyVolumeValue(
  value: string | undefined,
  bid: number | undefined,
  ask: number | undefined
): boolean {
  return isLikelyQuantityValue(value, bid, ask);
}

function numericField(row: MarketWatchRow, name: string): string | undefined {
  const value = cleanNumericCellValue(row[name]);
  return value && value.length > 0 ? value : undefined;
}

function normalizeMarketWatchText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function formatExtractionDebugSummary(debug: MarketWatchExtractionDebug): string[] {
  const lines = [
    'Sentinel-CSE ATrad observe-once read-only row debug',
    `Candidate Market Watch tables/sections found: ${debug.candidateCount}`
  ];

  if (debug.dojoDebug) {
    lines.push(`Detected Dojo watchgrid count: ${debug.dojoDebug.gridCount}`);
    lines.push(`Dojo grid view count: ${debug.dojoDebug.viewCount}`);
    lines.push('First 5 Dojo view summaries:');
    debug.dojoDebug.viewSummaries.slice(0, 5).forEach((view) => {
      lines.push(`Dojo view ${view.viewIndex}: rows=${view.rowCount}`);
      view.firstRows.forEach((row, rowIndex) => {
        lines.push(`  View row ${rowIndex + 1}: ${JSON.stringify(row)}`);
      });
    });
    lines.push('First 10 Dojo row text chunks:');
    debug.dojoDebug.sampleRows.forEach((row, index) => {
      lines.push(`Dojo row ${index + 1}: ${JSON.stringify(row)}`);
    });
    lines.push('First 10 Dojo parsed row objects:');
    debug.dojoDebug.parsedRows.forEach((row, index) => {
      lines.push(`Dojo parsed row ${index + 1}: ${JSON.stringify(row)}`);
    });
  }

  if (!debug.chosenCandidate) {
    lines.push('Chosen table/section score: none');
    if (debug.broadScan) {
      lines.push('Broad visible table/grid scan');
      lines.push(`Visible table count: ${debug.broadScan.visibleTableCount}`);
      lines.push(`Visible tr count: ${debug.broadScan.visibleTrCount}`);
      lines.push(`Visible role=grid count: ${debug.broadScan.visibleRoleGridCount}`);
      lines.push(`Visible role=table count: ${debug.broadScan.visibleRoleTableCount}`);
      lines.push(`Visible role=row count: ${debug.broadScan.visibleRoleRowCount}`);
      debug.broadScan.tableSummaries.forEach((table) => {
        lines.push(
          `Table ${table.index}: rows=${table.rowCount}, keywords=${
            table.keywordMatches.join(' | ') || 'none'
          }, nearby=${table.nearbyTextSnippet || 'n/a'}`
        );
        table.firstRows.forEach((row, rowIndex) => {
          lines.push(`  Row ${rowIndex + 1}: ${JSON.stringify(row)}`);
        });
      });
      debug.broadScan.gridSummaries.forEach((grid) => {
        lines.push(
          `Grid ${grid.index}: ${grid.typeHint}, keywords=${
            grid.keywordMatches.join(' | ') || 'none'
          }, nearby=${grid.nearbyTextSnippet || 'n/a'}`
        );
        lines.push(`  Child text: ${JSON.stringify(grid.childTextChunks)}`);
      });
    }
    if (debug.headerMatches && debug.headerMatches.length > 0) {
      lines.push('Header text search fallback');
      debug.headerMatches.forEach((match, index) => {
        lines.push(
          `Header ${index + 1}: ${match.text} [${match.tagName}] role=${match.role || 'n/a'} class=${match.className || 'n/a'}`
        );
        lines.push(`  Ancestor text: ${match.ancestorTextSnippet || 'n/a'}`);
        lines.push(`  Ancestor chain: ${match.ancestorTagChain || 'n/a'}`);
      });
    }
    return lines;
  }

  lines.push(`Chosen table/section score: ${debug.chosenCandidate.score}`);
  lines.push(
    `Chosen header row cells: ${JSON.stringify(debug.chosenCandidate.headerCells)}`
  );
  lines.push(
    `Chosen table keyword matches: ${
      debug.chosenCandidate.containerTextMatches.join(' | ') || 'none'
    }`
  );
  lines.push('First 10 visible data row cell arrays:');
  debug.chosenCandidate.sampleRows.forEach((row, index) => {
    lines.push(`Row ${index + 1}: ${JSON.stringify(row)}`);
  });
  debug.chosenCandidate.rowAnalyses.forEach((row, index) => {
    lines.push(
      `Row ${index + 1} (${row.cellCount} cells): ${row.accepted ? 'accepted' : 'rejected'}`
    );
    if (!row.accepted) {
      lines.push(`  Reasons: ${row.reasons.join(' | ')}`);
    }
    if (row.sanitizerIssueCodes && row.sanitizerIssueCodes.length > 0) {
      lines.push(`  Sanitizer issue codes: ${row.sanitizerIssueCodes.join(', ')}`);
    }
  });

  return lines;
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
    rejected: [],
    qualityAssessments: [],
    qualitySummary: emptyQualitySummary()
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

async function extractMarketWatchTableCandidates(
  page: ManualATradPageLike
): Promise<{
  chosenCandidateIndex: number;
  candidates: Array<{
    kind: 'table' | 'dojo-grid';
    score: number;
    headerRowIndex: number;
    headerCells: string[];
    rows: string[][];
    containerTextMatches: string[];
  }>;
  dojoCandidates: Array<{
    kind: 'dojo-grid';
    score: number;
    headerRowIndex: number;
    headerCells: string[];
    rows: string[][];
    containerTextMatches: string[];
    viewCount: number;
    viewSummaries: DojoGridViewSummary[];
  }>;
  broadScan: MarketWatchExtractionDebug['broadScan'];
  headerMatches: HeaderSearchMatch[];
}> {
  return page.evaluate(BROWSER_SAFE_MARKET_WATCH_EXTRACTION_DEBUG_EVALUATION);
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

const BROWSER_SAFE_MARKET_WATCH_EXTRACTION_DEBUG_EVALUATION = `(() => {
  const allowedHeaders = ${JSON.stringify(MARKET_WATCH_HEADERS)};
  const preferredKeywords = ${JSON.stringify(PREFERRED_MARKET_WATCH_KEYWORDS)};
  const headerSearchTerms = ['Security', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'];

  function normalize(value) {
    return String(value || '').replace(/\\s+/g, ' ').trim();
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  function snippet(value, maxLength) {
    const normalized = normalize(value);
    return normalized.length > maxLength ? normalized.slice(0, maxLength) : normalized;
  }

  function collectRows(table) {
    return Array.from(table.querySelectorAll('tr')).filter(isVisible);
  }

  function collectRowCells(row) {
    const directCells = Array.from(row.children).filter((child) =>
      child.tagName === 'TD' || child.tagName === 'TH'
    );
    const cells = directCells.length > 0 ? directCells : Array.from(row.querySelectorAll('td,th'));
    return cells.map((cell) => normalize(cell.textContent));
  }

  function tableContextText(table) {
    const container =
      table.closest('section,article,main,[role="region"],div') || table.parentElement || table;
    const siblingText = Array.from((container ? container.children : []) || [])
      .filter((element) => element !== table)
      .slice(0, 5)
      .map((element) => normalize(element.textContent))
      .join(' ');
    return normalize((container ? container.textContent : table.textContent) + ' ' + siblingText);
  }

  function scoreTableGroup(tables, index) {
    const visibleTables = tables.filter(isVisible);
    const headerCandidates = visibleTables.flatMap((table) =>
      collectRows(table).slice(0, 5).map((row, rowIndex) => ({
        table,
        rowIndex,
        cells: collectRowCells(row)
      }))
    );

    if (headerCandidates.length === 0) {
      return null;
    }

    let bestHeader = null;
    let bestHeaderScore = 0;
    for (const candidate of headerCandidates) {
      const headerScore = candidate.cells.filter((header) => allowedHeaders.includes(header)).length;
      if (headerScore > bestHeaderScore) {
        bestHeader = candidate;
        bestHeaderScore = headerScore;
      }
    }

    if (!bestHeader) {
      return null;
    }

    const headers = bestHeader.cells;
    const hasEssentialHeaders =
      headers.includes('Security') &&
      headers.includes('Bid Qty') &&
      headers.includes('Bid Price') &&
      headers.includes('Ask Price') &&
      headers.includes('Ask Qty') &&
      headers.includes('Last');
    if (!hasEssentialHeaders) {
      return null;
    }

    const contextText = visibleTables.map((table) => tableContextText(table)).join(' ');
    const keywordMatches = preferredKeywords.filter((keyword) =>
      contextText.toLowerCase().includes(keyword.toLowerCase())
    );
    const bodyRows = visibleTables.flatMap((table) => {
      const rows = collectRows(table);
      const startIndex = table === bestHeader.table ? bestHeader.rowIndex + 1 : 0;
      return rows.slice(startIndex).map((row) => collectRowCells(row));
    });
    if (bodyRows.length === 0) {
      return null;
    }

    return {
      kind: 'table',
      score: bestHeaderScore * 10 + keywordMatches.length,
      headerRowIndex: bestHeader.rowIndex,
      headerCells: headers,
      containerTextMatches: keywordMatches,
      rows: bodyRows
    };
  }

  function collectContainerHeaders(container) {
    const visibleTables = Array.from(container.querySelectorAll('table')).filter(isVisible);
    const headers = [];
    visibleTables.forEach((table) => {
      collectRows(table)
        .slice(0, 3)
        .forEach((row) => {
          collectRowCells(row).forEach((cell) => {
            if (allowedHeaders.includes(cell) && !headers.includes(cell)) {
              headers.push(cell);
            }
          });
        });
    });
    return headers;
  }

  function collectTextChunks(elements) {
    const chunks = [];
    elements.forEach((element) => {
      const text = normalize(element.textContent);
      if (text && !chunks.includes(text)) {
        chunks.push(text);
      }
    });
    return chunks;
  }

  function collectDojoCellChunks(row) {
    const visibleCells = Array.from(
      row.querySelectorAll('.dojoxGridCell, td, th, span, div')
    ).filter((element) => isVisible(element));
    const preferredCells = visibleCells.filter((element) =>
      element.classList.contains('dojoxGridCell') ||
      element.tagName === 'TD' ||
      element.tagName === 'TH'
    );
    const cells = preferredCells.length > 0 ? preferredCells : visibleCells;
    return collectTextChunks(cells);
  }

  function collectDojoRowsFromView(view) {
    const rowElements = Array.from(
      view.querySelectorAll('.dojoxGridContent [class*="dojoxGridRow"], .dojoxGridRowTable [class*="dojoxGridRow"], [class*="dojoxGridRow"]')
    ).filter((row) => isVisible(row));
    const logicalRows = [];

    rowElements.forEach((row) => {
      const cells = collectDojoCellChunks(row);
      const rowText = normalize(row.textContent).toLowerCase();
      if (
        cells.length === 0 ||
        cells.every((cell) => allowedHeaders.includes(cell)) ||
        rowText.includes('security') && rowText.includes('bid') && rowText.includes('ask')
      ) {
        return;
      }

      logicalRows.push(cells);
    });

    return logicalRows;
  }

  function mergeDojoViewRows(viewRows) {
    const rowCount = viewRows.reduce((max, rows) => Math.max(max, rows.length), 0);
    const mergedRows = [];

    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      const merged = [];
      viewRows.forEach((rows) => {
        const row = rows[rowIndex] || [];
        row.forEach((cell) => {
          if (cell) {
            merged.push(cell);
          }
        });
      });

      if (merged.length > 0) {
        mergedRows.push(merged);
      }
    }

    return mergedRows;
  }

  function dedupeMergedDojoRows(rows) {
    const deduped = [];
    const bestByTicker = new Map();

    function rowScore(row) {
      return row.reduce((score, cell) => {
        if (!cell) return score;
        return score + (/\\d/.test(cell) ? 2 : 1);
      }, 0);
    }

    rows.forEach((row) => {
      const tickerCell = row.find((cell) => /\\b[A-Z0-9]{2,12}\\.N\\d{4}\\b/.test(cell));
      const key = tickerCell || JSON.stringify(row);
      const existingIndex = bestByTicker.get(key);
      if (existingIndex === undefined) {
        bestByTicker.set(key, deduped.length);
        deduped.push(row);
        return;
      }

      if (rowScore(row) > rowScore(deduped[existingIndex])) {
        deduped[existingIndex] = row;
      }
    });

    return deduped;
  }

  function scoreDojoGrid(grid) {
    const className = String(grid.className || '');
    if (!/dojoxGrid/i.test(className)) {
      return null;
    }

    const container = grid.closest('section,article,main,[role="region"],div') || grid.parentElement || grid;
    const contextText = normalize(container ? container.textContent : grid.textContent);
    const keywordMatches = preferredKeywords.filter((keyword) =>
      contextText.toLowerCase().includes(keyword.toLowerCase())
    );
    if (
      !contextText.toLowerCase().includes('security') ||
      !contextText.toLowerCase().includes('last') ||
      !contextText.toLowerCase().includes('volume')
    ) {
      return null;
    }

    const headerCells = collectContainerHeaders(container);
    const views = Array.from(grid.querySelectorAll('.dojoxGridView')).filter(isVisible);
    const viewRows = (views.length > 0 ? views : [grid]).map((view) => collectDojoRowsFromView(view));
    const rows = dedupeMergedDojoRows(mergeDojoViewRows(viewRows)).filter(
      (row) => row.length > 0 && row.some((cell) => !allowedHeaders.includes(cell))
    );
    if (rows.length === 0) {
      return null;
    }

    const viewSummaries = viewRows.map((rows, viewIndex) => ({
      viewIndex,
      rowCount: rows.length,
      firstRows: rows.slice(0, 3)
    }));

    return {
      kind: 'dojo-grid',
      score: keywordMatches.length * 20 + (/watchgrid/i.test(className) ? 20 : 0),
      headerRowIndex: 0,
      headerCells,
      containerTextMatches: keywordMatches,
      rows,
      viewCount: views.length > 0 ? views.length : 1,
      viewSummaries
    };
  }

  function summarizeTable(table, index) {
    const rows = collectRows(table);
    const contextText = tableContextText(table);
    return {
      index,
      nearbyTextSnippet: snippet(contextText, 160),
      rowCount: rows.length,
      firstRows: rows.slice(0, 3).map((row) => collectRowCells(row)),
      keywordMatches: ['Security', 'Bid', 'Ask', 'Last', 'Volume'].filter((keyword) =>
        contextText.toLowerCase().includes(keyword.toLowerCase())
      )
    };
  }

  function summarizeGrid(element, index) {
    const text = normalize(element.textContent);
    return {
      index,
      typeHint: [
        element.tagName.toLowerCase(),
        element.getAttribute('role') || '',
        snippet(element.className || '', 40)
      ]
        .filter(Boolean)
        .join('.'),
      nearbyTextSnippet: snippet(text, 160),
      childTextChunks: Array.from(element.children)
        .filter(isVisible)
        .slice(0, 5)
        .map((child) => snippet(child.textContent, 80))
        .filter(Boolean),
      keywordMatches: ['Security', 'Bid', 'Ask', 'Last', 'Volume'].filter((keyword) =>
        text.toLowerCase().includes(keyword.toLowerCase())
      )
    };
  }

  function collectHeaderMatches() {
    const elements = Array.from(document.querySelectorAll('*')).filter(isVisible);
    const matches = [];
    for (const element of elements) {
      const text = normalize(element.textContent);
      if (!text) continue;
      const matchedTerm = headerSearchTerms.find((term) => text === term || text.includes(term));
      if (!matchedTerm) continue;

      const chain = [];
      let current = element;
      for (let index = 0; index < 5 && current; index += 1) {
        chain.push(current.tagName.toLowerCase());
        current = current.parentElement;
      }

      const ancestor = element.parentElement || element;
      matches.push({
        text: matchedTerm,
        tagName: element.tagName.toLowerCase(),
        role: element.getAttribute('role') || '',
        className: snippet(element.className || '', 40),
        ancestorTextSnippet: snippet(ancestor.textContent, 160),
        ancestorTagChain: chain.join('>')
      });
      if (matches.length >= 20) break;
    }
    return matches;
  }

  const tables = Array.from(document.querySelectorAll('table')).filter(isVisible);
  const containerCandidates = Array.from(
    document.querySelectorAll('section,article,main,[role="region"],div')
  )
    .filter(isVisible)
    .map((container) => Array.from(container.querySelectorAll(':scope table')).filter(isVisible))
    .filter((group) => group.length > 1)
    .map((group, index) => scoreTableGroup(group, index))
    .filter(Boolean)
    .sort((left, right) => right.score - left.score);
  const tableCandidates = tables
    .map((table, index) => scoreTableGroup([table], index))
    .filter(Boolean)
    .sort((left, right) => right.score - left.score);
  const dojoCandidates = Array.from(document.querySelectorAll('div,section,article'))
    .filter(isVisible)
    .map((element) => scoreDojoGrid(element))
    .filter(Boolean)
    .sort((left, right) => right.score - left.score);
  const scoredTables = [...containerCandidates, ...tableCandidates, ...dojoCandidates].sort(
    (left, right) => right.score - left.score
  );
  const gridElements = Array.from(document.querySelectorAll('[role="grid"],[role="table"],[role="row"],[class*="dojoxGrid"]'))
    .filter(isVisible)
    .filter((element) => element.tagName !== 'TABLE');

  return {
    chosenCandidateIndex: scoredTables.length > 0 ? 0 : -1,
    candidates: scoredTables,
    dojoCandidates,
    broadScan: {
      visibleTableCount: tables.length,
      visibleTrCount: Array.from(document.querySelectorAll('tr')).filter(isVisible).length,
      visibleRoleGridCount: Array.from(document.querySelectorAll('[role="grid"]')).filter(isVisible).length,
      visibleRoleTableCount: Array.from(document.querySelectorAll('[role="table"]')).filter(isVisible).length,
      visibleRoleRowCount: Array.from(document.querySelectorAll('[role="row"]')).filter(isVisible).length,
      tableSummaries: tables.slice(0, 20).map((table, index) => summarizeTable(table, index)),
      gridSummaries: gridElements.slice(0, 20).map((element, index) => summarizeGrid(element, index))
    },
    headerMatches: collectHeaderMatches()
  };
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
