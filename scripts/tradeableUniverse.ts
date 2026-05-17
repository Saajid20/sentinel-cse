import { readFile } from 'node:fs/promises';
import type { MarketSnapshot } from '@sentinel/core';

export type TradeableUniverseConfidence =
  | 'HIGH_CONFIDENCE'
  | 'MEDIUM_CONFIDENCE'
  | 'LOW_CONFIDENCE'
  | 'REJECTED';

export interface TradeableUniverseRules {
  excludeRightsAndWarrants: boolean;
  excludeNonVoting: boolean;
  minimumAverageVolume: number | null;
  maximumSpreadPercent: number | null;
  minimumSnapshotsPerSession: number | null;
  minimumConfidence: TradeableUniverseConfidence | null;
}

export interface TradeableUniverseConfig {
  name: string;
  description?: string;
  includeTickers: string[];
  excludeTickers: string[];
  excludePatterns: string[];
  rules: TradeableUniverseRules;
}

export interface TradeableUniverseSnapshotLike extends MarketSnapshot {
  metadata?: Record<string, unknown>;
}

export interface TradeableUniverseExclusion<T extends TradeableUniverseSnapshotLike> {
  snapshot: T;
  reasons: string[];
}

export interface TradeableUniverseReasonCount {
  reason: string;
  count: number;
}

export interface TradeableUniverseCoverageSummary {
  universeName: string;
  originalSnapshots: number;
  filteredSnapshots: number;
  excludedByUniverse: number;
  originalUniqueTickers: number;
  filteredUniqueTickers: number;
  topExcludedReasons: TradeableUniverseReasonCount[];
}

export interface TradeableUniverseFilterResult<T extends TradeableUniverseSnapshotLike> {
  snapshots: T[];
  excluded: TradeableUniverseExclusion<T>[];
  coverage: TradeableUniverseCoverageSummary;
}

const TICKER_PATTERN = /^[A-Z0-9]{2,12}\.[A-Z]\d{4}$/;
const CONFIDENCE_RANK: Record<TradeableUniverseConfidence, number> = {
  REJECTED: 0,
  LOW_CONFIDENCE: 1,
  MEDIUM_CONFIDENCE: 2,
  HIGH_CONFIDENCE: 3
};

export async function loadTradeableUniverseConfig(path: string): Promise<TradeableUniverseConfig> {
  const contents = await readFile(path, 'utf8');
  return parseTradeableUniverseConfig(contents, path);
}

export function parseTradeableUniverseConfig(
  contents: string,
  source = 'tradeable universe config'
): TradeableUniverseConfig {
  let parsed: unknown;
  try {
    parsed = JSON.parse(contents);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Malformed tradeable universe config ${source}: ${message}`);
  }

  return normalizeTradeableUniverseConfig(parsed, source);
}

export function isTickerAllowedByUniverse(ticker: string, config: TradeableUniverseConfig): boolean {
  return explainTickerUniverseDecision(ticker, config).length === 0;
}

export function filterSnapshotsByTradeableUniverse<T extends TradeableUniverseSnapshotLike>(
  snapshots: T[],
  config: TradeableUniverseConfig
): TradeableUniverseFilterResult<T> {
  const accepted: T[] = [];
  const excluded: TradeableUniverseExclusion<T>[] = [];

  for (const snapshot of snapshots) {
    const reasons = explainSnapshotUniverseDecision(snapshot, config);
    if (reasons.length === 0) {
      accepted.push(snapshot);
    } else {
      excluded.push({ snapshot, reasons });
    }
  }

  return {
    snapshots: accepted,
    excluded,
    coverage: summarizeTradeableUniverseCoverage(snapshots, accepted, excluded, config)
  };
}

export function summarizeTradeableUniverseCoverage<T extends TradeableUniverseSnapshotLike>(
  originalSnapshots: T[],
  filteredSnapshots: T[],
  excluded: TradeableUniverseExclusion<T>[],
  config: TradeableUniverseConfig
): TradeableUniverseCoverageSummary {
  const reasonCounts = new Map<string, number>();
  for (const entry of excluded) {
    for (const reason of entry.reasons) {
      reasonCounts.set(reason, (reasonCounts.get(reason) ?? 0) + 1);
    }
  }

  return {
    universeName: config.name,
    originalSnapshots: originalSnapshots.length,
    filteredSnapshots: filteredSnapshots.length,
    excludedByUniverse: excluded.length,
    originalUniqueTickers: uniqueTickerCount(originalSnapshots),
    filteredUniqueTickers: uniqueTickerCount(filteredSnapshots),
    topExcludedReasons: [...reasonCounts.entries()]
      .map(([reason, count]) => ({ reason, count }))
      .sort((left, right) => right.count - left.count || left.reason.localeCompare(right.reason))
      .slice(0, 5)
  };
}

export function findInvalidUniverseTickerEntries(config: TradeableUniverseConfig): string[] {
  return [...config.includeTickers, ...config.excludeTickers].filter((ticker) => !TICKER_PATTERN.test(ticker));
}

function explainSnapshotUniverseDecision(
  snapshot: TradeableUniverseSnapshotLike,
  config: TradeableUniverseConfig
): string[] {
  const reasons = explainTickerUniverseDecision(snapshot.ticker, config);
  const spreadPercent = calculateSpreadPercent(snapshot);
  if (
    config.rules.maximumSpreadPercent !== null &&
    spreadPercent !== undefined &&
    spreadPercent > config.rules.maximumSpreadPercent
  ) {
    reasons.push('spread above maximum');
  }

  const averageVolume = readNumericMetadata(snapshot, ['averageVolume', 'averageVolumeEstimate']);
  if (
    config.rules.minimumAverageVolume !== null &&
    averageVolume !== undefined &&
    averageVolume < config.rules.minimumAverageVolume
  ) {
    reasons.push('average volume below minimum');
  }

  const confidence = readConfidenceStatus(snapshot);
  if (
    config.rules.minimumConfidence !== null &&
    confidence !== undefined &&
    CONFIDENCE_RANK[confidence] < CONFIDENCE_RANK[config.rules.minimumConfidence]
  ) {
    reasons.push('confidence below minimum');
  }

  return reasons;
}

function explainTickerUniverseDecision(ticker: string, config: TradeableUniverseConfig): string[] {
  const normalizedTicker = normalizeTicker(ticker);
  const reasons: string[] = [];

  if (config.includeTickers.length > 0 && !config.includeTickers.includes(normalizedTicker)) {
    reasons.push('not in includeTickers');
  }

  if (config.excludeTickers.includes(normalizedTicker)) {
    reasons.push('excluded ticker');
  }

  const matchedPattern = config.excludePatterns.find((pattern) => normalizedTicker.includes(pattern));
  if (matchedPattern) {
    reasons.push(`matched exclude pattern ${matchedPattern}`);
  }

  if (config.rules.excludeRightsAndWarrants && isRightsOrWarrantTicker(normalizedTicker)) {
    reasons.push('rights/warrants excluded');
  }

  if (config.rules.excludeNonVoting && isNonVotingTicker(normalizedTicker)) {
    reasons.push('non-voting excluded');
  }

  return reasons;
}

function normalizeTradeableUniverseConfig(value: unknown, source: string): TradeableUniverseConfig {
  if (!isRecord(value)) {
    throw new Error(`Malformed tradeable universe config ${source}: root object is invalid.`);
  }

  const rules = value.rules;
  if (!isRecord(rules)) {
    throw new Error(`Malformed tradeable universe config ${source}: rules object is required.`);
  }

  return {
    name: readRequiredString(value, 'name', source),
    description: readOptionalString(value, 'description', source),
    includeTickers: readStringArray(value, 'includeTickers', source).map(normalizeTicker),
    excludeTickers: readStringArray(value, 'excludeTickers', source).map(normalizeTicker),
    excludePatterns: readStringArray(value, 'excludePatterns', source).map((pattern) =>
      pattern.trim().toUpperCase()
    ),
    rules: {
      excludeRightsAndWarrants: readRequiredBoolean(rules, 'excludeRightsAndWarrants', source),
      excludeNonVoting: readRequiredBoolean(rules, 'excludeNonVoting', source),
      minimumAverageVolume: readNullableNonNegativeNumber(rules, 'minimumAverageVolume', source),
      maximumSpreadPercent: readNullableNonNegativeNumber(rules, 'maximumSpreadPercent', source),
      minimumSnapshotsPerSession: readNullableNonNegativeInteger(rules, 'minimumSnapshotsPerSession', source),
      minimumConfidence: readNullableConfidence(rules, 'minimumConfidence', source)
    }
  };
}

function readRequiredString(value: Record<string, unknown>, key: string, source: string): string {
  const entry = value[key];
  if (typeof entry !== 'string' || entry.trim().length === 0) {
    throw new Error(`Malformed tradeable universe config ${source}: ${key} must be a non-empty string.`);
  }
  return entry.trim();
}

function readOptionalString(
  value: Record<string, unknown>,
  key: string,
  source: string
): string | undefined {
  const entry = value[key];
  if (entry === undefined) {
    return undefined;
  }
  if (typeof entry !== 'string') {
    throw new Error(`Malformed tradeable universe config ${source}: ${key} must be a string.`);
  }
  return entry.trim();
}

function readStringArray(value: Record<string, unknown>, key: string, source: string): string[] {
  const entry = value[key];
  if (!Array.isArray(entry) || entry.some((item) => typeof item !== 'string')) {
    throw new Error(`Malformed tradeable universe config ${source}: ${key} must be a string array.`);
  }
  return entry.map((item) => item.trim()).filter((item) => item.length > 0);
}

function readRequiredBoolean(value: Record<string, unknown>, key: string, source: string): boolean {
  const entry = value[key];
  if (typeof entry !== 'boolean') {
    throw new Error(`Malformed tradeable universe config ${source}: rules.${key} must be boolean.`);
  }
  return entry;
}

function readNullableNonNegativeNumber(
  value: Record<string, unknown>,
  key: string,
  source: string
): number | null {
  const entry = value[key];
  if (entry === null) {
    return null;
  }
  if (typeof entry !== 'number' || !Number.isFinite(entry) || entry < 0) {
    throw new Error(`Malformed tradeable universe config ${source}: rules.${key} must be a non-negative number or null.`);
  }
  return entry;
}

function readNullableNonNegativeInteger(
  value: Record<string, unknown>,
  key: string,
  source: string
): number | null {
  const entry = readNullableNonNegativeNumber(value, key, source);
  if (entry !== null && !Number.isInteger(entry)) {
    throw new Error(`Malformed tradeable universe config ${source}: rules.${key} must be an integer or null.`);
  }
  return entry;
}

function readNullableConfidence(
  value: Record<string, unknown>,
  key: string,
  source: string
): TradeableUniverseConfidence | null {
  const entry = value[key];
  if (entry === null) {
    return null;
  }
  if (typeof entry !== 'string' || !isTradeableUniverseConfidence(entry)) {
    throw new Error(`Malformed tradeable universe config ${source}: rules.${key} is invalid.`);
  }
  return entry;
}

function readConfidenceStatus(snapshot: TradeableUniverseSnapshotLike): TradeableUniverseConfidence | undefined {
  const metadata = snapshot.metadata;
  const candidates = [
    readRecordString(snapshot, 'qualityStatus'),
    readRecordString(snapshot, 'confidence'),
    readRecordString(snapshot, 'status'),
    metadata ? readRecordString(metadata, 'qualityStatus') : undefined,
    metadata ? readRecordString(metadata, 'confidence') : undefined,
    metadata ? readRecordString(metadata, 'status') : undefined
  ];

  return candidates.find((candidate): candidate is TradeableUniverseConfidence =>
    candidate !== undefined && isTradeableUniverseConfidence(candidate)
  );
}

function readNumericMetadata(
  snapshot: TradeableUniverseSnapshotLike,
  keys: string[]
): number | undefined {
  const metadata = snapshot.metadata;
  if (!metadata) {
    return undefined;
  }

  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string') {
      const parsed = Number(value.replace(/,/g, '').trim());
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}

function readRecordString(value: object, key: string): string | undefined {
  const entry = (value as Record<string, unknown>)[key];
  return typeof entry === 'string' ? entry.trim().toUpperCase() : undefined;
}

function calculateSpreadPercent(snapshot: TradeableUniverseSnapshotLike): number | undefined {
  if (snapshot.bestAsk <= 0 || !Number.isFinite(snapshot.bestBid) || !Number.isFinite(snapshot.bestAsk)) {
    return undefined;
  }
  return ((snapshot.bestAsk - snapshot.bestBid) / snapshot.bestAsk) * 100;
}

function uniqueTickerCount(snapshots: TradeableUniverseSnapshotLike[]): number {
  return new Set(snapshots.map((snapshot) => snapshot.ticker)).size;
}

function isRightsOrWarrantTicker(ticker: string): boolean {
  const classCode = ticker.split('.')[1] ?? '';
  return classCode.startsWith('R') || classCode.startsWith('W');
}

function isNonVotingTicker(ticker: string): boolean {
  const classCode = ticker.split('.')[1] ?? '';
  return classCode.startsWith('X');
}

function isTradeableUniverseConfidence(value: string): value is TradeableUniverseConfidence {
  return value === 'HIGH_CONFIDENCE' ||
    value === 'MEDIUM_CONFIDENCE' ||
    value === 'LOW_CONFIDENCE' ||
    value === 'REJECTED';
}

function normalizeTicker(ticker: string): string {
  return ticker.trim().toUpperCase();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
