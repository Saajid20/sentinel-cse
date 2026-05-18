import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ManualATradCompareSessionsRuntime } from './manualATradCompareSessions.js';
import {
  buildSessionComparisonRecommendations,
  createManualATradCompareSessionsConfig,
  formatATradSessionComparisonSummary,
  runManualATradCompareSessions
} from './manualATradCompareSessions.js';

const sessionA = {
  sessionId: 'atrad-session-short',
  startedAt: '2026-05-08T10:15:00.000Z',
  endedAt: '2026-05-08T10:15:30.000Z',
  source: 'atrad-full-watch-equity',
  mode: 'read-only-local-recording',
  confidencePolicy: 'HIGH_CONFIDENCE only',
  intervalSeconds: 15,
  durationSeconds: 30,
  totals: {
    ticksAttempted: 2,
    rawRowsExtracted: 4,
    usableSnapshots: 2,
    quarantinedSnapshots: 1,
    rejectedSnapshots: 1
  },
  snapshots: [
    {
      ticker: 'AAA.N0000',
      timestamp: 1_715_160_000_000,
      lastPrice: 10.1,
      bestBid: 10,
      bestAsk: 10.2,
      bidDepth: 1000,
      askDepth: 900,
      volume: 1000,
      totalTurnover: 10100,
      source: 'atrad-market-watch'
    },
    {
      ticker: 'BBB.N0000',
      timestamp: 1_715_160_015_000,
      lastPrice: 25.1,
      bestBid: 25,
      bestAsk: 25.2,
      bidDepth: 800,
      askDepth: 700,
      volume: 900,
      totalTurnover: 22590,
      source: 'atrad-market-watch'
    }
  ],
  diagnostics: []
};

const sessionB = {
  sessionId: 'atrad-session-longer',
  startedAt: '2026-05-08T10:15:00.000Z',
  endedAt: '2026-05-08T10:17:00.000Z',
  source: 'atrad-full-watch-equity',
  mode: 'read-only-local-recording',
  confidencePolicy: 'HIGH_CONFIDENCE only',
  intervalSeconds: 10,
  durationSeconds: 120,
  totals: {
    ticksAttempted: 3,
    rawRowsExtracted: 6,
    usableSnapshots: 4,
    quarantinedSnapshots: 1,
    rejectedSnapshots: 1
  },
  snapshots: [
    {
      ticker: 'AAA.N0000',
      timestamp: 1_715_160_000_000,
      lastPrice: 10.1,
      bestBid: 10,
      bestAsk: 10.1,
      bidDepth: 1200,
      askDepth: 600,
      volume: 1000,
      totalTurnover: 10100,
      source: 'atrad-market-watch'
    },
    {
      ticker: 'AAA.N0000',
      timestamp: 1_715_160_010_000,
      lastPrice: 10.3,
      bestBid: 10.2,
      bestAsk: 10.3,
      bidDepth: 1300,
      askDepth: 500,
      volume: 3000,
      totalTurnover: 30900,
      source: 'atrad-market-watch'
    },
    {
      ticker: 'AAA.N0000',
      timestamp: 1_715_160_020_000,
      lastPrice: 10.5,
      bestBid: 10.4,
      bestAsk: 10.5,
      bidDepth: 1400,
      askDepth: 400,
      volume: 6000,
      totalTurnover: 63000,
      source: 'atrad-market-watch'
    },
    {
      ticker: 'CCC.N0000',
      timestamp: 1_715_160_030_000,
      lastPrice: 40.1,
      bestBid: 40,
      bestAsk: 40.1,
      bidDepth: 1500,
      askDepth: 900,
      volume: 2000,
      totalTurnover: 80200,
      source: 'atrad-market-watch'
    }
  ],
  diagnostics: []
};

describe('manual ATrad compare-sessions helpers', () => {
  it('accepts repeated --input values', () => {
    const config = createManualATradCompareSessionsConfig([
      '--input',
      'one.json',
      '--input',
      'two.json'
    ]);

    expect(config).toEqual({
      inputPaths: ['one.json', 'two.json'],
      readonlyMode: true
    });
  });

  it('accepts comma-separated --inputs values', () => {
    const config = createManualATradCompareSessionsConfig(['--inputs', 'one.json,two.json']);

    expect(config.inputPaths).toEqual(['one.json', 'two.json']);
  });

  it('accepts an optional universe path', () => {
    const config = createManualATradCompareSessionsConfig([
      '--input',
      'one.json',
      '--universe',
      'universe.json'
    ]);

    expect(config).toEqual({
      inputPaths: ['one.json'],
      universePath: 'universe.json',
      readonlyMode: true
    });
  });

  it('rejects missing inputs', () => {
    expect(() => createManualATradCompareSessionsConfig([])).toThrow(
      'Missing required --input <path> or --inputs <path1,path2,...> for ATrad session comparison.'
    );
  });

  it('loads two fake session fixtures and compares readiness', async () => {
    const calls: string[] = [];
    const runtime: ManualATradCompareSessionsRuntime = {
      async readFile(path) {
        if (path === 'short.json') return JSON.stringify(sessionA);
        if (path === 'longer.json') return JSON.stringify(sessionB);
        throw new Error('ENOENT');
      },
      log(message) {
        calls.push(message);
      }
    };

    const result = await runManualATradCompareSessions(
      createManualATradCompareSessionsConfig(['--input', 'short.json', '--input', 'longer.json']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.sessions).toHaveLength(2);
    expect(result.sessions[0]?.sessionId).toBe('atrad-session-short');
    expect(result.sessions[1]?.sessionId).toBe('atrad-session-longer');
    expect(result.sessions[0]?.readinessStatus).toBe('NOT_READY');
    expect(result.sessions[1]?.readinessStatus).toBe('PARTIALLY_READY');
    expect(result.sessions[1]?.strategyReadySnapshots).toBeGreaterThan(result.sessions[0]?.strategyReadySnapshots ?? 0);
    expect(calls.join('\n')).toContain('Sentinel-CSE ATrad recorded session comparison');
  });

  it('detects a top blocker and aggregate recommendations', async () => {
    const runtime: ManualATradCompareSessionsRuntime = {
      async readFile(path) {
        return path === 'short.json' ? JSON.stringify(sessionA) : JSON.stringify(sessionB);
      },
      log() {}
    };

    const result = await runManualATradCompareSessions(
      createManualATradCompareSessionsConfig(['--input', 'short.json', '--input', 'longer.json']),
      runtime
    );

    expect(result.sessions[0]?.topBlocker).toBeTruthy();
    expect(result.recommendations).toContain('record longer session');
    expect(result.recommendations).toContain('reduce interval seconds');
    expect(result.recommendations).toContain('run replay experiment variants');
  });

  it('applies a tradeable universe filter when provided', async () => {
    const runtime: ManualATradCompareSessionsRuntime = {
      async readFile(path) {
        if (path === 'short.json') return JSON.stringify(sessionA);
        if (path === 'longer.json') return JSON.stringify(sessionB);
        if (path === 'universe.json') {
          return JSON.stringify({
            name: 'compare-universe',
            includeTickers: ['AAA.N0000'],
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
          });
        }
        throw new Error('ENOENT');
      },
      log() {}
    };

    const result = await runManualATradCompareSessions(
      createManualATradCompareSessionsConfig([
        '--input',
        'short.json',
        '--input',
        'longer.json',
        '--universe',
        'universe.json'
      ]),
      runtime
    );

    expect(result.universeName).toBe('compare-universe');
    expect(result.sessions[0]?.totalSnapshotsLoaded).toBe(2);
    expect(result.sessions[0]?.replayedSnapshots).toBe(1);
    expect(result.sessions[0]?.universeCoverage?.excludedByUniverse).toBe(1);
    expect(result.sessions[1]?.totalSnapshotsLoaded).toBe(4);
    expect(result.sessions[1]?.replayedSnapshots).toBe(3);
    expect(result.sessions[1]?.universeCoverage?.filteredSnapshots).toBe(3);
  });

  it('formats a comparison summary', () => {
    const summary = formatATradSessionComparisonSummary({
      ok: true,
      message: 'done',
      sessions: [
        {
          inputPath: 'short.json',
          sessionId: 'atrad-session-short',
          startedAt: sessionA.startedAt,
          endedAt: sessionA.endedAt,
          durationSeconds: 30,
          totalSnapshotsLoaded: 2,
          uniqueTickers: 2,
          replayedSnapshots: 2,
          enrichedSnapshots: 2,
          snapshotsWithVwapEstimate: 2,
          snapshotsWithFirstFiveMinuteHighEstimate: 0,
          snapshotsWithVolumeRatioEstimate: 0,
          snapshotsWithOrderBookImbalance: 2,
          strategyReadySnapshots: 0,
          readinessStatus: 'NOT_READY',
          signalsGenerated: 0,
          outcomesClosed: 0,
          topBlocker: 'insufficient time-series history',
          topTickers: [{ ticker: 'AAA.N0000', snapshotCount: 1 }],
          diagnostics: {} as never,
          universeCoverage: {
            universeName: 'compare-universe',
            originalSnapshots: 2,
            filteredSnapshots: 1,
            excludedByUniverse: 1,
            originalUniqueTickers: 2,
            filteredUniqueTickers: 1,
            topExcludedReasons: [{ reason: 'not in includeTickers', count: 1 }]
          }
        }
      ],
      recommendations: ['record longer session'],
      universeName: 'compare-universe'
    });

    expect(summary).toContain('Sentinel-CSE ATrad recorded session comparison');
    expect(summary).toContain('Tradeable universe: compare-universe');
    expect(summary.join('\n')).toContain('excluded by universe: 1');
    expect(summary.join('\n')).toContain('readiness status: NOT_READY');
    expect(summary).toContain('Aggregate recommendations:');
  });

  it('builds aggregate recommendations directly', () => {
    const recommendations = buildSessionComparisonRecommendations([
      {
        inputPath: 'short.json',
        sessionId: 'atrad-session-short',
        startedAt: sessionA.startedAt,
        endedAt: sessionA.endedAt,
        durationSeconds: 30,
        totalSnapshotsLoaded: 2,
        uniqueTickers: 2,
        replayedSnapshots: 2,
        enrichedSnapshots: 2,
        snapshotsWithVwapEstimate: 2,
        snapshotsWithFirstFiveMinuteHighEstimate: 0,
        snapshotsWithVolumeRatioEstimate: 0,
        snapshotsWithOrderBookImbalance: 2,
        strategyReadySnapshots: 0,
        readinessStatus: 'NOT_READY',
        signalsGenerated: 0,
        outcomesClosed: 0,
        topBlocker: 'insufficient time-series history',
        topTickers: [{ ticker: 'AAA.N0000', snapshotCount: 1 }],
        diagnostics: {
          tickersWithRepeatedSnapshots: 0
        } as never
      },
      {
        inputPath: 'longer.json',
        sessionId: 'atrad-session-longer',
        startedAt: sessionB.startedAt,
        endedAt: sessionB.endedAt,
        durationSeconds: 120,
        totalSnapshotsLoaded: 4,
        uniqueTickers: 2,
        replayedSnapshots: 4,
        enrichedSnapshots: 4,
        snapshotsWithVwapEstimate: 4,
        snapshotsWithFirstFiveMinuteHighEstimate: 2,
        snapshotsWithVolumeRatioEstimate: 2,
        snapshotsWithOrderBookImbalance: 4,
        strategyReadySnapshots: 1,
        readinessStatus: 'PARTIALLY_READY',
        signalsGenerated: 0,
        outcomesClosed: 0,
        topBlocker: 'first-5-minute high missing',
        topTickers: [{ ticker: 'AAA.N0000', snapshotCount: 3 }],
        diagnostics: {
          tickersWithRepeatedSnapshots: 1
        } as never
      }
    ]);

    expect(recommendations).toContain('record longer session');
    expect(recommendations).toContain('reduce interval seconds');
    expect(recommendations).toContain('focus on tickers with repeated observations');
    expect(recommendations).toContain('run replay experiment variants');
  });

  it('rejects invalid input paths at runtime', async () => {
    const runtime: ManualATradCompareSessionsRuntime = {
      async readFile() {
        throw new Error('ENOENT');
      },
      log() {}
    };

    await expect(
      runManualATradCompareSessions(
        createManualATradCompareSessionsConfig(['--input', 'missing.json']),
        runtime
      )
    ).rejects.toThrow('Unable to read recorded ATrad session file: missing.json');
  });

  it('does not read environment variables or include live action strings', () => {
    const source = readFileSync('scripts/manualATradCompareSessions.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/telegram|supabase/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|market order|limit order/i);
  });

  it('does not introduce live action strings in replay diagnostics code', () => {
    const source = readFileSync('scripts/manualATradReplaySession.ts', 'utf8');

    expect(source).not.toMatch(/telegram|supabase/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|market order|limit order/i);
  });
});
