import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  filterSnapshotsByTradeableUniverse,
  isTickerAllowedByUniverse,
  loadTradeableUniverseConfig,
  parseTradeableUniverseConfig,
  type TradeableUniverseConfig,
  type TradeableUniverseSnapshotLike
} from './tradeableUniverse.js';

const baseConfig: TradeableUniverseConfig = {
  name: 'unit-test-universe',
  description: 'Synthetic test universe',
  includeTickers: [],
  excludeTickers: [],
  excludePatterns: ['.R0000', '.U0000'],
  rules: {
    excludeRightsAndWarrants: true,
    excludeNonVoting: false,
    minimumAverageVolume: null,
    maximumSpreadPercent: 5,
    minimumSnapshotsPerSession: 3,
    minimumConfidence: 'HIGH_CONFIDENCE'
  }
};

const sampleSnapshot: TradeableUniverseSnapshotLike = {
  ticker: 'ALFA.N0000',
  timestamp: 1,
  lastPrice: 10,
  bestBid: 9.9,
  bestAsk: 10,
  bidDepth: 1000,
  askDepth: 900,
  volume: 1000,
  totalTurnover: 10000,
  metadata: { qualityStatus: 'HIGH_CONFIDENCE' }
};

describe('tradeable universe helpers', () => {
  it('loads a valid config from disk', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'sentinel-universe-'));
    const path = join(dir, 'universe.json');
    await writeFile(path, JSON.stringify(baseConfig), 'utf8');

    const config = await loadTradeableUniverseConfig(path);

    expect(config.name).toBe('unit-test-universe');
    expect(config.excludePatterns).toEqual(['.R0000', '.U0000']);
  });

  it('loads the checked-in example config', async () => {
    const config = await loadTradeableUniverseConfig('config/tradeableUniverse.example.json');

    expect(config.name).toBe('default-cse-tradeable-universe');
    expect(config.rules.maximumSpreadPercent).toBe(5);
  });

  it('rejects malformed config', () => {
    expect(() => parseTradeableUniverseConfig('{not-json')).toThrow(
      'Malformed tradeable universe config'
    );
    expect(() => parseTradeableUniverseConfig(JSON.stringify({ name: 'bad' }))).toThrow(
      'rules object is required'
    );
  });

  it('allows only includeTickers when include list is non-empty', () => {
    const config = { ...baseConfig, includeTickers: ['ALFA.N0000'] };

    expect(isTickerAllowedByUniverse('ALFA.N0000', config)).toBe(true);
    expect(isTickerAllowedByUniverse('BETA.N0000', config)).toBe(false);
  });

  it('blocks excludeTickers', () => {
    const config = { ...baseConfig, excludeTickers: ['BETA.N0000'] };

    expect(isTickerAllowedByUniverse('BETA.N0000', config)).toBe(false);
  });

  it('blocks excludePatterns for rights and units', () => {
    expect(isTickerAllowedByUniverse('ALFA.R0000', baseConfig)).toBe(false);
    expect(isTickerAllowedByUniverse('ALFA.U0000', baseConfig)).toBe(false);
  });

  it('excludes rights and warrants when enabled', () => {
    expect(isTickerAllowedByUniverse('ALFA.R0001', baseConfig)).toBe(false);
    expect(isTickerAllowedByUniverse('ALFA.W0000', baseConfig)).toBe(false);
  });

  it('excludes non-voting tickers only when enabled', () => {
    expect(isTickerAllowedByUniverse('HNB.X0000', baseConfig)).toBe(true);
    expect(
      isTickerAllowedByUniverse('HNB.X0000', {
        ...baseConfig,
        rules: { ...baseConfig.rules, excludeNonVoting: true }
      })
    ).toBe(false);
  });

  it('filters snapshots by spread and confidence when those fields are available', () => {
    const result = filterSnapshotsByTradeableUniverse(
      [
        sampleSnapshot,
        { ...sampleSnapshot, ticker: 'WIDE.N0000', bestBid: 9, bestAsk: 10 },
        {
          ...sampleSnapshot,
          ticker: 'LOWC.N0000',
          metadata: { qualityStatus: 'MEDIUM_CONFIDENCE' }
        }
      ],
      baseConfig
    );

    expect(result.snapshots.map((snapshot) => snapshot.ticker)).toEqual(['ALFA.N0000']);
    expect(result.coverage.excludedByUniverse).toBe(2);
    expect(result.coverage.topExcludedReasons.map((entry) => entry.reason)).toEqual(
      expect.arrayContaining(['spread above maximum', 'confidence below minimum'])
    );
  });

  it('does not introduce external service or action boundaries', async () => {
    const helperSource = await readFile('scripts/tradeableUniverse.ts', 'utf8');
    const validateSource = await readFile('scripts/validateTradeableUniverse.ts', 'utf8');
    const source = `${helperSource}\n${validateSource}`;

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/telegram|supabase/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|market order|limit order/i);
  });
});
