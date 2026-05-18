import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ManualATradReplaySessionRuntime } from './manualATradReplaySession.js';
import {
  analyzeATradReplayDiagnostics,
  analyzeATradStrategyConditionDiagnostics,
  buildATradReplayFeatures,
  createManualATradReplaySessionConfig,
  extractReplayableATradSnapshots,
  formatATradReplaySessionSummary,
  parseATradRecordedSessionFile,
  runManualATradReplaySession,
  topTickersBySnapshotCount
} from './manualATradReplaySession.js';

const fakeRecordedSession = {
  sessionId: 'atrad-session-20260508-101500',
  startedAt: '2026-05-08T10:15:00.000Z',
  endedAt: '2026-05-08T10:16:00.000Z',
  source: 'atrad-full-watch-equity',
  mode: 'read-only-local-recording',
  confidencePolicy: 'HIGH_CONFIDENCE only',
  intervalSeconds: 15,
  durationSeconds: 60,
  totals: {
    ticksAttempted: 2,
    rawRowsExtracted: 6,
    usableSnapshots: 3,
    quarantinedSnapshots: 1,
    rejectedSnapshots: 1
  },
  snapshots: [
    {
      ticker: 'BETA.N0000',
      timestamp: 1_715_160_030_000,
      lastPrice: 55.1,
      bestBid: 55,
      bestAsk: 55.2,
      bidDepth: 1000,
      askDepth: 700,
      volume: 15000,
      totalTurnover: 826500,
      source: 'atrad-market-watch',
      metadata: { companyName: 'Beta PLC' }
    },
    {
      ticker: 'ALFA.N0000',
      timestamp: 1_715_160_000_000,
      lastPrice: 41.5,
      bestBid: 41.4,
      bestAsk: 41.6,
      bidDepth: 900,
      askDepth: 600,
      volume: 12000,
      totalTurnover: 498000,
      source: 'atrad-market-watch',
      metadata: { companyName: 'Alfa PLC' }
    },
    {
      ticker: 'ALFA.N0000',
      timestamp: 1_715_160_015_000,
      lastPrice: 41.6,
      bestBid: 41.5,
      bestAsk: 41.7,
      bidDepth: 950,
      askDepth: 650,
      volume: 13000,
      totalTurnover: 540800,
      source: 'atrad-market-watch',
      metadata: { companyName: 'Alfa PLC' }
    }
  ],
  diagnostics: [
    {
      tickNumber: 1,
      capturedAt: '2026-05-08T10:15:00.000Z',
      rawRowsExtracted: 3,
      acceptedSnapshots: 2,
      usableSnapshots: 2,
      quarantinedSnapshots: 1,
      rejectedSnapshots: 0
    }
  ],
  quarantinedRows: [
    {
      tickNumber: 1,
      ticker: 'GAMM.N0000',
      status: 'LOW_CONFIDENCE',
      issueCodes: ['LOW_MAPPING_CONFIDENCE']
    }
  ]
};

describe('manual ATrad replay-session helpers', () => {
  it('parses the input CLI flag', () => {
    const config = createManualATradReplaySessionConfig(['--input', 'data/live-sessions/example.json']);

    expect(config).toEqual({
      inputPath: 'data/live-sessions/example.json',
      readonlyMode: true
    });
  });

  it('parses an optional universe CLI flag', () => {
    const config = createManualATradReplaySessionConfig([
      '--input',
      'data/live-sessions/example.json',
      '--universe',
      'config/universe.json'
    ]);

    expect(config).toEqual({
      inputPath: 'data/live-sessions/example.json',
      universePath: 'config/universe.json',
      readonlyMode: true
    });
  });

  it('parses the condition diagnostics flag', () => {
    const config = createManualATradReplaySessionConfig([
      '--input',
      'data/live-sessions/example.json',
      '--condition-diagnostics'
    ]);

    expect(config).toEqual({
      inputPath: 'data/live-sessions/example.json',
      conditionDiagnostics: true,
      readonlyMode: true
    });
  });

  it('rejects a missing input path', () => {
    expect(() => createManualATradReplaySessionConfig([])).toThrow(
      'Missing required --input <path> for ATrad session replay.'
    );
  });

  it('loads a valid recorded session fixture', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));

    expect(session.sessionId).toBe('atrad-session-20260508-101500');
    expect(session.snapshots).toHaveLength(3);
  });

  it('rejects malformed session JSON', () => {
    expect(() => parseATradRecordedSessionFile('{not-json')).toThrow('Malformed ATrad session JSON');
    expect(() => parseATradRecordedSessionFile(JSON.stringify({ sessionId: 'x' }))).toThrow(
      'Malformed ATrad session JSON: source is required.'
    );
  });

  it('extracts usable snapshots only and sorts them by timestamp', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const snapshots = extractReplayableATradSnapshots(session);

    expect(snapshots).toHaveLength(3);
    expect(snapshots.map((snapshot) => snapshot.ticker)).toEqual([
      'ALFA.N0000',
      'ALFA.N0000',
      'BETA.N0000'
    ]);
    expect(snapshots.map((snapshot) => snapshot.timestamp)).toEqual([
      1_715_160_000_000,
      1_715_160_015_000,
      1_715_160_030_000
    ]);
  });

  it('enriches snapshots in timestamp order and computes observation counts', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const enriched = buildATradReplayFeatures(extractReplayableATradSnapshots(session));

    expect(enriched.map((snapshot) => snapshot.ticker)).toEqual([
      'ALFA.N0000',
      'ALFA.N0000',
      'BETA.N0000'
    ]);
    expect(enriched.map((snapshot) => snapshot.replayFeatures.observationCount)).toEqual([1, 2, 1]);
  });

  it('computes spread percent order book imbalance and volume delta', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const enriched = buildATradReplayFeatures(extractReplayableATradSnapshots(session));

    expect(enriched[0]?.replayFeatures.spreadPercent).toBeCloseTo(((41.6 - 41.4) / 41.6) * 100, 5);
    expect(enriched[0]?.replayFeatures.orderBookImbalance).toBeCloseTo((900 - 600) / (900 + 600), 5);
    expect(enriched[1]?.replayFeatures.volumeDeltaFromPrevious).toBe(1000);
  });

  it('computes a volume ratio estimate from prior observations', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const enriched = buildATradReplayFeatures(extractReplayableATradSnapshots(session));

    expect(enriched[1]?.replayFeatures.volumeRatioEstimate).toBeCloseTo(13000 / 12000, 5);
  });

  it('uses metadata.vwa when valid and falls back to turnover over volume when valid', () => {
    const session = parseATradRecordedSessionFile(
      JSON.stringify({
        ...fakeRecordedSession,
        snapshots: [
          {
            ...fakeRecordedSession.snapshots[0],
            metadata: { companyName: 'Beta PLC', vwa: '55.05', turnover: '826500' }
          },
          {
            ...fakeRecordedSession.snapshots[1],
            metadata: { companyName: 'Alfa PLC', turnover: '498000' }
          }
        ]
      })
    );
    const enriched = buildATradReplayFeatures(extractReplayableATradSnapshots(session));

    expect(enriched[0]?.replayFeatures.vwapEstimate).toBeCloseTo(41.5, 5);
    expect(enriched[1]?.replayFeatures.vwapEstimate).toBeCloseTo(55.05, 5);
  });

  it('omits bad vwap estimates and approximates first5MinHigh from session highs', () => {
    const session = parseATradRecordedSessionFile(
      JSON.stringify({
        ...fakeRecordedSession,
        snapshots: [
          {
            ...fakeRecordedSession.snapshots[1],
            metadata: { companyName: 'Alfa PLC', vwa: '9999', turnover: '99999999' }
          },
          fakeRecordedSession.snapshots[2]
        ]
      })
    );
    const enriched = buildATradReplayFeatures(extractReplayableATradSnapshots(session));

    expect(enriched[0]?.replayFeatures.vwapEstimate).toBeUndefined();
    expect(enriched[1]?.replayFeatures.first5MinHighEstimate).toBeCloseTo(41.5, 5);
  });

  it('counts unique tickers and top tickers by snapshot count', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const snapshots = extractReplayableATradSnapshots(session);
    const topTickers = topTickersBySnapshotCount(snapshots);

    expect(new Set(snapshots.map((snapshot) => snapshot.ticker)).size).toBe(2);
    expect(topTickers).toEqual([
      { ticker: 'ALFA.N0000', snapshotCount: 2 },
      { ticker: 'BETA.N0000', snapshotCount: 1 }
    ]);
  });

  it('rejects a missing input file path at runtime', async () => {
    const runtime: ManualATradReplaySessionRuntime = {
      async readFile() {
        throw new Error('ENOENT');
      },
      log() {}
    };

    await expect(
      runManualATradReplaySession(
        createManualATradReplaySessionConfig(['--input', 'missing.json']),
        runtime
      )
    ).rejects.toThrow('Unable to read recorded ATrad session file: missing.json');
  });

  it('replays in safe SHADOW mode without sending alerts', async () => {
    const calls: string[] = [];
    const runtime: ManualATradReplaySessionRuntime = {
      async readFile() {
        return JSON.stringify(fakeRecordedSession);
      },
      log(message) {
        calls.push(message);
      }
    };

    const result = await runManualATradReplaySession(
      createManualATradReplaySessionConfig(['--input', 'fixture.json']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.totalSnapshotsLoaded).toBe(3);
    expect(result.uniqueTickers).toBe(2);
    expect(result.replaySummary.snapshotsProcessed).toBe(3);
    expect(result.replaySummary.alertsSent).toBe(0);
    expect(result.diagnostics.readinessStatus).toBe('PARTIALLY_READY');
    expect(result.diagnostics.tickersWithRepeatedSnapshots).toBe(1);
    expect(result.diagnostics.strategyReadySnapshotCount).toBe(1);
    expect(result.diagnostics.snapshotsWithVwapEstimate).toBe(3);
    expect(result.diagnostics.snapshotsWithFirstFiveMinuteHighEstimate).toBe(1);
    expect(result.diagnostics.snapshotsWithVolumeRatioEstimate).toBe(1);
    expect(result.warning).toBe('No signals were generated during replay.');
    expect(calls.join('\n')).toContain('Sentinel-CSE ATrad recorded session replay summary');
    expect(calls.join('\n')).toContain('ATrad replay diagnostics:');
  });

  it('applies a tradeable universe filter when provided', async () => {
    const calls: string[] = [];
    const runtime: ManualATradReplaySessionRuntime = {
      async readFile(path) {
        if (path === 'fixture.json') return JSON.stringify(fakeRecordedSession);
        if (path === 'universe.json') {
          return JSON.stringify({
            name: 'focused-universe',
            includeTickers: ['ALFA.N0000'],
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
      log(message) {
        calls.push(message);
      }
    };

    const result = await runManualATradReplaySession(
      createManualATradReplaySessionConfig(['--input', 'fixture.json', '--universe', 'universe.json']),
      runtime
    );

    expect(result.totalSnapshotsLoaded).toBe(3);
    expect(result.replaySummary.snapshotsProcessed).toBe(2);
    expect(result.uniqueTickers).toBe(1);
    expect(result.universeCoverage).toMatchObject({
      universeName: 'focused-universe',
      originalSnapshots: 3,
      filteredSnapshots: 2,
      excludedByUniverse: 1
    });
    expect(result.universeCoverage?.topExcludedReasons[0]).toEqual({
      reason: 'not in includeTickers',
      count: 1
    });
    expect(calls.join('\n')).toContain('- excluded by universe: 1');
  });

  it('reports diagnostics when no signals are generated', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const snapshots = extractReplayableATradSnapshots(session);
    const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, {
      snapshotsProcessed: 3,
      signalsGenerated: 0,
      generatedSignals: [],
      alertsSent: 0,
      outcomesClosed: 0,
      finalActiveSignals: []
    });

    expect(diagnostics.likelyBlockers).toContain('insufficient time-series history');
    expect(diagnostics.likelyBlockers).toContain('volume ratio unavailable');
    expect(diagnostics.likelyBlockers).toContain('first-5-minute high missing');
  });

  it('calculates repeated ticker count and average spread percent', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const snapshots = extractReplayableATradSnapshots(session);
    const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, {
      snapshotsProcessed: 3,
      signalsGenerated: 0,
      generatedSignals: [],
      alertsSent: 0,
      outcomesClosed: 0,
      finalActiveSignals: []
    });

    expect(diagnostics.tickersWithRepeatedSnapshots).toBe(1);
    expect(diagnostics.perTickerDiagnostics[0]).toMatchObject({
      ticker: 'ALFA.N0000',
      snapshots: 2,
      enoughObservations: true,
      strategyReady: true
    });
    expect(diagnostics.perTickerDiagnostics[0]?.averageSpreadPercent).toBeCloseTo(
      ((((41.6 - 41.4) / 41.6) * 100) + (((41.7 - 41.5) / 41.7) * 100)) / 2,
      5
    );
    expect(diagnostics.perTickerDiagnostics[1]).toMatchObject({
      ticker: 'BETA.N0000',
      snapshots: 1,
      enoughObservations: false,
      strategyReady: false
    });
  });

  it('classifies too-short unrepeated data as NOT_READY', () => {
    const session = parseATradRecordedSessionFile(
      JSON.stringify({
        ...fakeRecordedSession,
        snapshots: [
          { ...fakeRecordedSession.snapshots[0], ticker: 'ONE.N0000', timestamp: 1 },
          { ...fakeRecordedSession.snapshots[1], ticker: 'TWO.N0000', timestamp: 2 }
        ]
      })
    );
    const snapshots = extractReplayableATradSnapshots(session);
    const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, {
      snapshotsProcessed: 2,
      signalsGenerated: 0,
      generatedSignals: [],
      alertsSent: 0,
      outcomesClosed: 0,
      finalActiveSignals: []
    });

    expect(diagnostics.readinessStatus).toBe('NOT_READY');
  });

  it('classifies repeated clean data with missing strategy features as PARTIALLY_READY', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const snapshots = extractReplayableATradSnapshots(session);
    const diagnostics = analyzeATradReplayDiagnostics(session, snapshots, {
      snapshotsProcessed: 3,
      signalsGenerated: 0,
      generatedSignals: [],
      alertsSent: 0,
      outcomesClosed: 0,
      finalActiveSignals: []
    });

    expect(diagnostics.readinessStatus).toBe('PARTIALLY_READY');
  });

  it('does not print condition diagnostics by default', async () => {
    const calls: string[] = [];
    const runtime: ManualATradReplaySessionRuntime = {
      async readFile() {
        return JSON.stringify(fakeRecordedSession);
      },
      log(message) {
        calls.push(message);
      }
    };

    await runManualATradReplaySession(
      createManualATradReplaySessionConfig(['--input', 'fixture.json']),
      runtime
    );

    expect(calls.join('\n')).not.toContain('ATrad strategy condition diagnostics:');
  });

  it('prints condition diagnostics when requested and counts conditions per ticker', async () => {
    const calls: string[] = [];
    const runtime: ManualATradReplaySessionRuntime = {
      async readFile() {
        return JSON.stringify(fakeRecordedSession);
      },
      log(message) {
        calls.push(message);
      }
    };

    const result = await runManualATradReplaySession(
      createManualATradReplaySessionConfig([
        '--input',
        'fixture.json',
        '--condition-diagnostics'
      ]),
      runtime
    );

    expect(result.conditionDiagnostics).toBeDefined();
    expect(result.conditionDiagnostics?.perTicker[0]).toMatchObject({
      ticker: 'ALFA.N0000',
      snapshots: 2,
      sufficientHistory: 1,
      spreadPass: 2,
      vwapAvailable: 2,
      priceAboveVwap: 0,
      firstHighAvailable: 1,
      momentumPass: 1,
      volumeRatioAvailable: 1,
      volumeRatioPass: 0,
      imbalanceAvailable: 2,
      imbalancePass: 2,
      signals: 0
    });
    expect(calls.join('\n')).toContain('ATrad strategy condition diagnostics:');
    expect(calls.join('\n')).toContain(
      'ALFA.N0000 | 2/2 | 1/2 | 0/2 | 2/2 | 2/2 | 0/2 | 1/2 | 1/2 | 1/2 | 0/2 | 2/2 | 2/2 | 0/2'
    );
  });

  it('identifies top blockers by ticker from enriched replay features', () => {
    const session = parseATradRecordedSessionFile(JSON.stringify(fakeRecordedSession));
    const diagnostics = analyzeATradStrategyConditionDiagnostics(
      extractReplayableATradSnapshots(session),
      {
        snapshotsProcessed: 3,
        signalsGenerated: 0,
        generatedSignals: [],
        alertsSent: 0,
        outcomesClosed: 0,
        finalActiveSignals: []
      }
    );

    expect(diagnostics.thresholdSummary).toMatchObject({
      maxSpreadPercent: 1.5,
      minimumVolumeRatio: 2,
      minimumImbalance: 0
    });
    expect(diagnostics.perTicker[0]?.topBlockers).toEqual([
      'price below VWAP',
      'first high unavailable'
    ]);
  });

  it('formats a replay summary', () => {
    const summary = formatATradReplaySessionSummary({
      ok: true,
      message: 'done',
      sessionId: fakeRecordedSession.sessionId,
      source: fakeRecordedSession.source,
      startedAt: fakeRecordedSession.startedAt,
      endedAt: fakeRecordedSession.endedAt,
      totalSnapshotsLoaded: 3,
      uniqueTickers: 2,
      topTickers: [
        { ticker: 'ALFA.N0000', snapshotCount: 2 },
        { ticker: 'BETA.N0000', snapshotCount: 1 }
      ],
      replaySummary: {
        snapshotsProcessed: 3,
        signalsGenerated: 0,
        generatedSignals: [],
        alertsSent: 0,
        outcomesClosed: 0,
        finalActiveSignals: [],
        startTime: 1_715_160_000_000,
        endTime: 1_715_160_030_000
      },
      diagnostics: {
        snapshotsProcessed: 3,
        enrichedSnapshotsCount: 3,
        uniqueTickers: 2,
        tickersWithRepeatedSnapshots: 1,
        spreadBlockedCount: 0,
        volumeBlockedCount: 2,
        imbalanceBlockedCount: 0,
        vwapMissingCount: 0,
        firstFiveMinuteHighMissingCount: 2,
        priceNotAboveVwapCount: 0,
        priceNotAboveMomentumTriggerCount: 0,
        insufficientHistoryCount: 1,
        qualityGateExcludedCount: 2,
        snapshotsWithVwapEstimate: 3,
        snapshotsWithFirstFiveMinuteHighEstimate: 1,
        snapshotsWithVolumeRatioEstimate: 1,
        snapshotsWithOrderBookImbalance: 3,
        strategyGeneratedSignalCount: 0,
        strategyReadySnapshotCount: 1,
        likelyBlockers: ['insufficient time-series history', 'volume ratio unavailable'],
        recommendations: ['record longer session with interval <= 10s'],
        readinessStatus: 'PARTIALLY_READY',
        perTickerDiagnostics: [
          {
            ticker: 'ALFA.N0000',
            snapshots: 2,
            averageSpreadPercent: ((41.6 - 41.4) / 41.6) * 100,
            latestLastPrice: 41.6,
            latestBid: 41.5,
            latestAsk: 41.7,
            enoughObservations: true,
            strategyReady: true
          }
        ]
      },
      universeCoverage: {
        universeName: 'focused-universe',
        originalSnapshots: 3,
        filteredSnapshots: 2,
        excludedByUniverse: 1,
        originalUniqueTickers: 2,
        filteredUniqueTickers: 1,
        topExcludedReasons: [{ reason: 'not in includeTickers', count: 1 }]
      },
      warning: 'No signals were generated during replay.'
    });

    expect(summary).toContain('sessionId: atrad-session-20260508-101500');
    expect(summary).toContain('total snapshots loaded: 3');
    expect(summary).toContain('- excluded by universe: 1');
    expect(summary).toContain('warning: No signals were generated during replay.');
    expect(summary).toContain('ATrad replay diagnostics:');
    expect(summary).toContain('- readiness status: PARTIALLY_READY');
  });

  it('does not read environment variables or include live action strings', () => {
    const source = readFileSync('scripts/manualATradReplaySession.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/telegram|supabase/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|market order|limit order/i);
  });
});
