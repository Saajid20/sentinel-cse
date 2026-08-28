import { readdir, readFile, stat } from 'node:fs/promises';
import { basename, join } from 'node:path';

/**
 * Research evidence console data layer.
 *
 * Reads local R10/R11 runtime artifacts and assembles the review surface. This
 * module is strictly read-only and derives nothing that is not already present
 * in an artifact: it never recomputes a financial value, never fills a gap, and
 * never produces a trade label. Its integrity checks are data-provenance
 * observations about figures the analysis already recorded, not new analysis.
 */

export interface ResearchConsoleConfig {
  r11AnalysisDir: string;
  r11GoldLabelDir: string;
  r10RetrievalDir: string;
  json: boolean;
}

export interface ResearchConsoleRuntime {
  readdir(path: string): Promise<string[]>;
  readFile(path: string): Promise<string>;
  stat(path: string): Promise<{ isDirectory(): boolean; mtimeMs: number }>;
}

export type ReviewState =
  | 'CLEAN'
  | 'MANUAL_REVIEW'
  | 'INSUFFICIENT_EVIDENCE'
  | 'PARSE_GAP';

/** Whether a human decision can actually change this case's outcome. */
export type Actionability =
  | 'DECIDABLE'
  | 'RECOVERABLE'
  | 'SOURCE_LIMITED'
  | 'BLOCKED'
  | 'SETTLED';

export interface MetricFigure {
  metricName: string;
  value: number | null;
  current: number | null;
  previous: number | null;
  occurrenceCount: number | null;
  conflict: boolean;
}

export type IntegrityCode =
  | 'SIGN_FLIP_DENOMINATOR'
  | 'LIABILITIES_EXCEED_ASSETS'
  | 'NEGATIVE_EQUITY_UNSCORED';

export interface IntegrityFinding {
  code: IntegrityCode;
  field: string;
  verdict: string | null;
  severity: 'FLAG' | 'GUARD_HELD';
  detail: string;
  figures: MetricFigure[];
}

export interface EvidenceTrace {
  metricName: string;
  pageNumber: number | null;
  statementType: string | null;
  rowLabel: string | null;
  rawValue: string | null;
}

export interface ReviewQueueEntry {
  ticker: string;
  analysisPath: string;
  generatedAt: string | null;
  metricsPresent: number;
  metricsExpected: number;
  state: ReviewState;
  actionability: Actionability;
  missingMetrics: string[];
  manualReviewReasons: string[];
  hasConflicts: boolean;
  scorecard: Record<string, unknown>;
  figures: MetricFigure[];
  integrity: IntegrityFinding[];
  traces: EvidenceTrace[];
}

export interface GoldLabelSummary {
  total: number;
  names: string[];
}

export interface RetrievalDocument {
  title: string;
  score: number | null;
  documentDerived: string[];
  annotationDerived: string[];
}

export interface RetrievalSummary {
  resultPath: string;
  storePath: string | null;
  ticker: string | null;
  matchedCount: number;
  storedCount: number | null;
  documents: RetrievalDocument[];
}

export interface SourceStatus {
  path: string;
  exists: boolean;
  fileCount: number;
}

export interface ResearchConsoleSummary {
  generatedAt: string;
  safety: {
    mode: string;
    tradeLabels: string;
    orderPath: string;
    synthesizedValues: string;
    researchLabels: string[];
  };
  sources: {
    r11Analysis: SourceStatus;
    r11GoldLabels: SourceStatus;
    r10Retrieval: SourceStatus;
  };
  coverage: {
    tickersAnalysed: number;
    fullyRecovered: number;
    awaitingReview: number;
    goldLabels: number;
    integrityFlags: number;
  };
  reviewQueue: ReviewQueueEntry[];
  goldLabels: GoldLabelSummary;
  retrieval: RetrievalSummary | null;
}

const DEFAULT_R11_ANALYSIS_DIR = 'research/python/.r11_runtime/analysis';
const DEFAULT_R11_GOLD_LABEL_DIR = 'research/python/.r11_runtime/gold_labels';
const DEFAULT_R10_RETRIEVAL_DIR = '.runtime-pipeline/r10-local-retrieval-results';

/** The four core metrics an R11 case is expected to recover. */
const CORE_METRICS = [
  'group_profit_for_the_period_yoy_growth',
  'group_total_assets_growth',
  'group_total_liabilities_growth',
  'group_total_equity_growth'
] as const;

const TICKER_PATTERN = /([A-Z]{2,6})\.N\d{4}/;

export function createResearchConsoleConfig(args: string[] = []): ResearchConsoleConfig {
  return {
    r11AnalysisDir: readFlagValue(args, '--r11-analysis-dir') ?? DEFAULT_R11_ANALYSIS_DIR,
    r11GoldLabelDir: readFlagValue(args, '--r11-gold-label-dir') ?? DEFAULT_R11_GOLD_LABEL_DIR,
    r10RetrievalDir: readFlagValue(args, '--r10-retrieval-dir') ?? DEFAULT_R10_RETRIEVAL_DIR,
    json: args.includes('--json')
  };
}

export async function runResearchConsole(
  config: ResearchConsoleConfig = createResearchConsoleConfig(),
  runtime: ResearchConsoleRuntime = defaultRuntime()
): Promise<ResearchConsoleSummary> {
  const analysisFiles = await listJsonFiles(config.r11AnalysisDir, runtime);
  const goldLabelFiles = await listJsonFiles(config.r11GoldLabelDir, runtime);
  const retrievalFiles = await listJsonFiles(config.r10RetrievalDir, runtime);

  const reviewQueue = await buildReviewQueue(config.r11AnalysisDir, analysisFiles.files, runtime);
  const goldLabels = summariseGoldLabels(goldLabelFiles.files);
  const retrieval = await loadLatestRetrieval(config.r10RetrievalDir, retrievalFiles.files, runtime);

  const integrityFlags = reviewQueue.reduce(
    (total, entry) => total + entry.integrity.filter((finding) => finding.severity === 'FLAG').length,
    0
  );

  return {
    generatedAt: new Date().toISOString(),
    safety: {
      mode: 'research / read-only',
      tradeLabels: 'none emitted',
      orderPath: 'not reachable from this view',
      synthesizedValues: 'none — missing metrics stay missing',
      researchLabels: [
        'SUPPORT',
        'BLOCK',
        'MANUAL_REVIEW',
        'NO_EFFECT',
        'INSUFFICIENT_EVIDENCE'
      ]
    },
    sources: {
      r11Analysis: analysisFiles.status,
      r11GoldLabels: goldLabelFiles.status,
      r10Retrieval: retrievalFiles.status
    },
    coverage: {
      tickersAnalysed: reviewQueue.length,
      fullyRecovered: reviewQueue.filter((entry) => entry.state === 'CLEAN').length,
      awaitingReview: reviewQueue.filter((entry) => entry.state !== 'CLEAN').length,
      goldLabels: goldLabels.total,
      integrityFlags
    },
    reviewQueue,
    goldLabels,
    retrieval
  };
}

async function buildReviewQueue(
  dir: string,
  files: string[],
  runtime: ResearchConsoleRuntime
): Promise<ReviewQueueEntry[]> {
  const newestByTicker = new Map<string, ReviewQueueEntry>();

  for (const file of files) {
    const path = join(dir, file);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(await runtime.readFile(path)) as Record<string, unknown>;
    } catch {
      // A malformed or partially written artifact is skipped rather than
      // guessed at. Reporting a case we could not read as though it analysed
      // cleanly would be worse than omitting it.
      continue;
    }

    const ticker = extractTicker(parsed, file);
    if (!ticker) {
      continue;
    }

    const entry = buildEntry(ticker, path, parsed);
    const existing = newestByTicker.get(ticker);
    if (!existing || isNewer(entry.generatedAt, existing.generatedAt)) {
      newestByTicker.set(ticker, entry);
    }
  }

  return [...newestByTicker.values()].sort(compareQueueEntries);
}

function buildEntry(
  ticker: string,
  path: string,
  parsed: Record<string, unknown>
): ReviewQueueEntry {
  const scorecardResult = asRecord(parsed.scorecard_build_result);
  const scorecard = asRecord(scorecardResult.scorecard);
  const missingMetrics = asStringArray(scorecardResult.missing_expected_metrics);
  const manualReviewReasons = asStringArray(scorecardResult.manual_review_reasons);
  const aggregated = asArray(parsed.aggregated_metric_results);

  const figures = aggregated.map(toMetricFigure).filter((figure): figure is MetricFigure => figure !== null);
  const coreFigures = figures.filter((figure) => (CORE_METRICS as readonly string[]).includes(figure.metricName));
  const hasConflicts = figures.some((figure) => figure.conflict);
  const manualReviewRequired = scorecard.manual_review_required === true;

  const state = deriveState({
    manualReviewRequired,
    metricsPresent: coreFigures.length,
    aggregatedCount: figures.length
  });

  const integrity = findIntegrityIssues(scorecard, figures, manualReviewReasons);

  return {
    ticker,
    analysisPath: path,
    generatedAt: typeof parsed.generated_at === 'string' ? parsed.generated_at : null,
    metricsPresent: coreFigures.length,
    metricsExpected: CORE_METRICS.length,
    state,
    actionability: deriveActionability(state, missingMetrics, integrity, figures.length),
    missingMetrics,
    manualReviewReasons,
    hasConflicts,
    scorecard,
    figures,
    integrity,
    traces: collectTraces(aggregated)
  };
}

function deriveState(input: {
  manualReviewRequired: boolean;
  metricsPresent: number;
  aggregatedCount: number;
}): ReviewState {
  if (input.aggregatedCount === 0) {
    return 'INSUFFICIENT_EVIDENCE';
  }
  if (!input.manualReviewRequired) {
    return 'CLEAN';
  }
  return input.metricsPresent <= 1 ? 'PARSE_GAP' : 'MANUAL_REVIEW';
}

/**
 * Actionability answers "can a person change this outcome today?", which is a
 * different question from "how incomplete is it?". A case missing three metrics
 * because the filing never published them is not more actionable than a clean
 * case whose verdict is disputed — it is less. A clean case with nothing raised
 * against it is SETTLED: it needs no one, and must not crowd the top of the queue.
 */
function deriveActionability(
  state: ReviewState,
  missingMetrics: string[],
  integrity: IntegrityFinding[],
  aggregatedCount: number
): Actionability {
  if (aggregatedCount === 0) {
    return 'BLOCKED';
  }
  // A questioned verdict or a held guard is precisely what a human is for.
  if (integrity.length > 0) {
    return 'DECIDABLE';
  }
  if (state === 'CLEAN') {
    return 'SETTLED';
  }
  // Liabilities absent alongside other gaps is the signature of a filing that
  // never labelled the row; no parser change reaches it.
  if (missingMetrics.includes('group_total_liabilities_growth') && missingMetrics.length > 1) {
    return 'SOURCE_LIMITED';
  }
  return 'RECOVERABLE';
}

/**
 * Integrity checks. Each reads only values the analysis already stored and
 * reports a provenance concern about how a verdict was reached. None of them
 * recompute, replace or infer a financial figure.
 */
function findIntegrityIssues(
  scorecard: Record<string, unknown>,
  figures: MetricFigure[],
  manualReviewReasons: string[]
): IntegrityFinding[] {
  const findings: IntegrityFinding[] = [];
  const equity = figures.find((figure) => figure.metricName === 'group_total_equity_growth');
  const assets = figures.find((figure) => figure.metricName === 'group_total_assets_growth');
  const liabilities = figures.find((figure) => figure.metricName === 'group_total_liabilities_growth');

  const capitalStrength = asStringOrNull(scorecard.capital_strength);
  const balanceSheetRisk = asStringOrNull(scorecard.balance_sheet_risk);

  if (
    capitalStrength !== null &&
    equity?.previous !== null &&
    equity?.current !== null &&
    equity !== undefined &&
    equity.previous! < 0 &&
    equity.current! > 0
  ) {
    findings.push({
      code: 'SIGN_FLIP_DENOMINATOR',
      field: 'capital_strength',
      verdict: capitalStrength,
      severity: 'FLAG',
      detail:
        'Equity crossed zero between periods, so the growth percentage is a sign flip in the denominator rather than a proportional strengthening. The verdict rests on that percentage.',
      figures: [equity]
    });
  }

  if (
    capitalStrength === null &&
    equity?.current !== null &&
    equity !== undefined &&
    equity.current! <= 0
  ) {
    findings.push({
      code: 'NEGATIVE_EQUITY_UNSCORED',
      field: 'capital_strength',
      verdict: null,
      severity: 'GUARD_HELD',
      detail:
        manualReviewReasons.find((reason) => /equity/i.test(reason)) ??
        'Capital strength declined to score because current group equity is not positive.',
      figures: [equity]
    });
  }

  if (
    balanceSheetRisk !== null &&
    assets?.current !== null &&
    liabilities?.current !== null &&
    assets !== undefined &&
    liabilities !== undefined &&
    liabilities.current! > assets.current!
  ) {
    findings.push({
      code: 'LIABILITIES_EXCEED_ASSETS',
      field: 'balance_sheet_risk',
      verdict: balanceSheetRisk,
      severity: 'FLAG',
      detail:
        'Liabilities exceed assets, but the verdict compares growth rates rather than levels, so the imbalance does not reach the score.',
      figures: [assets, liabilities]
    });
  }

  return findings;
}

function collectTraces(aggregated: Record<string, unknown>[]): EvidenceTrace[] {
  const traces: EvidenceTrace[] = [];
  for (const item of aggregated) {
    const metricName = asStringOrNull(item.metric_name);
    const selected = asRecord(item.selected_metric);
    const sourceTraces = asArray(selected.source_traces);
    const first = sourceTraces[0];
    if (!metricName || !first) {
      continue;
    }
    traces.push({
      metricName,
      pageNumber: asNumberOrNull(first.page_number),
      statementType: asStringOrNull(first.table_id),
      rowLabel: asStringOrNull(first.row_label),
      rawValue: asStringOrNull(first.raw_value)
    });
  }
  return traces;
}

function toMetricFigure(item: Record<string, unknown>): MetricFigure | null {
  const metricName = asStringOrNull(item.metric_name);
  if (!metricName) {
    return null;
  }
  const selected = asRecord(item.selected_metric);
  const inputs = asRecord(asRecord(item.selected_audit_entry).inputs);
  return {
    metricName,
    value: asNumberOrNull(selected.value),
    current: asNumberOrNull(inputs.current),
    previous: asNumberOrNull(inputs.previous),
    occurrenceCount: asNumberOrNull(item.occurrence_count),
    conflict: item.conflict === true
  };
}

function summariseGoldLabels(files: string[]): GoldLabelSummary {
  const names = files
    .filter((file) => file.endsWith('_gold_label.json'))
    .map((file) => file.replace(/_gold_label\.json$/, ''))
    .sort();
  return { total: names.length, names };
}

async function loadLatestRetrieval(
  dir: string,
  files: string[],
  runtime: ResearchConsoleRuntime
): Promise<RetrievalSummary | null> {
  // Prefer the most recently modified result so a post-fix rerun supersedes the
  // baseline it was compared against.
  let newest: { path: string; mtimeMs: number } | undefined;
  for (const file of files) {
    const path = join(dir, file);
    try {
      const stats = await runtime.stat(path);
      if (!newest || stats.mtimeMs > newest.mtimeMs) {
        newest = { path, mtimeMs: stats.mtimeMs };
      }
    } catch {
      continue;
    }
  }

  if (!newest) {
    return null;
  }

  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(await runtime.readFile(newest.path)) as Record<string, unknown>;
  } catch {
    return null;
  }

  const planSummary = asRecord(parsed.query_plan_summary);
  const documents = asArray(parsed.matched_documents).map((document) => {
    const reasons = asStringArray(document.matched_reasons);
    return {
      title: asStringOrNull(document.title) ?? 'untitled document',
      score: asNumberOrNull(document.score),
      // A ticker match can be satisfied by the tickers_hint we wrote at
      // ingestion, so it cannot be attributed to the document from this result
      // alone. Keyword matches can: since tickers_hint was removed from the
      // searchable text, a keyword only fires on the document's own words.
      documentDerived: reasons.filter((reason) => !isHintEligible(reason)),
      annotationDerived: reasons.filter(isHintEligible)
    };
  });

  return {
    resultPath: newest.path,
    storePath: asStringOrNull(parsed.document_store_path),
    ticker: asStringOrNull(planSummary.ticker),
    matchedCount: asNumberOrNull(parsed.matched_document_count) ?? documents.length,
    storedCount: null,
    documents
  };
}

function isHintEligible(reason: string): boolean {
  return reason.startsWith('ticker:');
}

function compareQueueEntries(a: ReviewQueueEntry, b: ReviewQueueEntry): number {
  const order: Record<Actionability, number> = {
    DECIDABLE: 0,
    RECOVERABLE: 1,
    SOURCE_LIMITED: 2,
    BLOCKED: 3,
    SETTLED: 4
  };
  const byActionability = order[a.actionability] - order[b.actionability];
  if (byActionability !== 0) {
    return byActionability;
  }
  const byFlags =
    b.integrity.filter((finding) => finding.severity === 'FLAG').length -
    a.integrity.filter((finding) => finding.severity === 'FLAG').length;
  if (byFlags !== 0) {
    return byFlags;
  }
  return a.ticker.localeCompare(b.ticker);
}

function extractTicker(parsed: Record<string, unknown>, fileName: string): string | null {
  const pdfPath = asStringOrNull(parsed.pdf_path);
  if (pdfPath) {
    const match = TICKER_PATTERN.exec(basename(pdfPath));
    if (match) {
      return match[1];
    }
  }
  const fromFile = TICKER_PATTERN.exec(fileName);
  if (fromFile) {
    return fromFile[1];
  }
  const prefix = /^([a-z]{2,6})_/.exec(fileName);
  return prefix ? prefix[1].toUpperCase() : null;
}

function isNewer(candidate: string | null, existing: string | null): boolean {
  if (!candidate) {
    return false;
  }
  if (!existing) {
    return true;
  }
  return Date.parse(candidate) > Date.parse(existing);
}

async function listJsonFiles(
  dir: string,
  runtime: ResearchConsoleRuntime
): Promise<{ files: string[]; status: SourceStatus }> {
  try {
    const entries = await runtime.readdir(dir);
    const files = entries.filter((entry) => entry.toLowerCase().endsWith('.json'));
    return { files, status: { path: dir, exists: true, fileCount: files.length } };
  } catch {
    return { files: [], status: { path: dir, exists: false, fileCount: 0 } };
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asStringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function defaultRuntime(): ResearchConsoleRuntime {
  return {
    readdir: async (path) => readdir(path),
    readFile: async (path) => readFile(path, 'utf8'),
    stat: async (path) => stat(path)
  };
}
