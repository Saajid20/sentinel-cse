import { mkdir, mkdtemp, readFile, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  createSentinelDashboardConfig,
  formatSentinelDashboard,
  runSentinelDashboard
} from './sentinelDashboard.js';

const baseSession = {
  sessionId: 'atrad-session-base',
  startedAt: '2026-05-08T10:15:00.000Z',
  endedAt: '2026-05-08T10:16:00.000Z',
  source: 'atrad-full-watch-equity',
  mode: 'read-only-local-recording',
  confidencePolicy: 'HIGH_CONFIDENCE only',
  intervalSeconds: 15,
  durationSeconds: 60,
  totals: {
    ticksAttempted: 4,
    rawRowsExtracted: 8,
    usableSnapshots: 3,
    quarantinedSnapshots: 1,
    rejectedSnapshots: 2
  },
  snapshots: [
    snapshot('ALFA.N0000', 1_715_160_000_000),
    snapshot('ALFA.N0000', 1_715_160_015_000),
    snapshot('BETA.N0000', 1_715_160_030_000)
  ],
  diagnostics: [
    diagnostic('OPEN'),
    diagnostic('CLOSED'),
    diagnostic('INACTIVE'),
    diagnostic('UNKNOWN')
  ]
};

const exampleUniverse = {
  name: 'example-universe',
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

describe('sentinel dashboard', () => {
  it('reports a missing live-sessions folder without failing', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'sentinel-dashboard-'));
    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        join(dir, 'missing-sessions'),
        '--example-universe',
        'config/tradeableUniverse.example.json'
      ])
    );
    const output = formatSentinelDashboard(summary);

    expect(summary.localFiles.exists).toBe(false);
    expect(summary.localFiles.sessionFileCount).toBe(0);
    expect(summary.latestSession).toBeUndefined();
    expect(output).toContain('folder exists: no');
    expect(output).toContain('latest session file: none');
    expect(output).toContain('Record an open-market ATrad session');
  });

  it('selects the latest session file by modification time', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'sentinel-dashboard-'));
    const sessionsDir = join(dir, 'sessions');
    await mkdir(sessionsDir);
    const oldPath = join(sessionsDir, 'atrad-session-old.json');
    const newPath = join(sessionsDir, 'atrad-session-new.json');
    await writeFile(oldPath, JSON.stringify({ ...baseSession, sessionId: 'old-session' }), 'utf8');
    await writeFile(newPath, JSON.stringify({ ...baseSession, sessionId: 'new-session' }), 'utf8');
    await utimes(oldPath, new Date('2026-05-08T10:00:00Z'), new Date('2026-05-08T10:00:00Z'));
    await utimes(newPath, new Date('2026-05-08T11:00:00Z'), new Date('2026-05-08T11:00:00Z'));

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        sessionsDir,
        '--example-universe',
        'config/tradeableUniverse.example.json'
      ])
    );

    expect(summary.localFiles.sessionFileCount).toBe(2);
    expect(summary.localFiles.latestSessionFilePath).toBe(newPath);
    expect(summary.latestSession?.sessionId).toBe('new-session');
  });

  it('summarizes latest session totals and market state counts', async () => {
    const { sessionsDir } = await writeSessionFixture(baseSession);
    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        sessionsDir,
        '--example-universe',
        'config/tradeableUniverse.example.json'
      ])
    );

    expect(summary.latestSession?.totals).toMatchObject({
      ticksAttempted: 4,
      usableSnapshots: 3,
      quarantinedSnapshots: 1,
      rejectedSnapshots: 2
    });
    expect(summary.latestSession?.marketStates).toEqual({
      OPEN: 1,
      CLOSED: 1,
      INACTIVE: 1,
      UNKNOWN: 1
    });
    expect(summary.latestSession?.replayReadiness).toMatchObject({
      snapshotsCount: 3,
      uniqueTickers: 2,
      repeatedTickersEstimate: 1,
      likelyUsefulForReplay: true
    });
  });

  it('reads a custom universe config when present', async () => {
    const { sessionsDir, dir } = await writeSessionFixture(baseSession);
    const customPath = join(dir, 'tradeableUniverse.json');
    await writeFile(
      customPath,
      JSON.stringify({
        ...exampleUniverse,
        name: 'custom-universe',
        includeTickers: ['ALFA.N0000', 'BETA.N0000'],
        rules: { ...exampleUniverse.rules, excludeNonVoting: true, maximumSpreadPercent: 4 }
      }),
      'utf8'
    );

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        sessionsDir,
        '--universe',
        customPath,
        '--example-universe',
        'config/tradeableUniverse.example.json'
      ])
    );

    expect(summary.tradeableUniverse.source).toBe('custom');
    expect(summary.tradeableUniverse.name).toBe('custom-universe');
    expect(summary.tradeableUniverse.includeTickersCount).toBe(2);
    expect(summary.tradeableUniverse.includedTickersPreview).toEqual(['ALFA.N0000', 'BETA.N0000']);
    expect(summary.tradeableUniverse.excludeNonVoting).toBe(true);
    expect(summary.tradeableUniverse.maximumSpreadPercent).toBe(4);
  });

  it('falls back to the example universe config when the custom config is missing', async () => {
    const { sessionsDir, dir } = await writeSessionFixture(baseSession);
    const examplePath = join(dir, 'tradeableUniverse.example.json');
    await writeFile(examplePath, JSON.stringify(exampleUniverse), 'utf8');

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        sessionsDir,
        '--universe',
        join(dir, 'missing-custom.json'),
        '--example-universe',
        examplePath
      ])
    );

    expect(summary.tradeableUniverse.source).toBe('example');
    expect(summary.tradeableUniverse.name).toBe('example-universe');
  });

  it('recommends recording during market open when the latest session only has CLOSED ticks', async () => {
    const { sessionsDir, dir } = await writeSessionFixture({
      ...baseSession,
      totals: { ...baseSession.totals, usableSnapshots: 0 },
      snapshots: [],
      diagnostics: [diagnostic('CLOSED'), diagnostic('CLOSED')]
    });
    const customPath = join(dir, 'tradeableUniverse.json');
    await writeFile(customPath, JSON.stringify(exampleUniverse), 'utf8');

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig(['--sessions-dir', sessionsDir, '--universe', customPath])
    );

    expect(summary.recommendation).toBe(
      'Record during market open; the latest session contains only CLOSED ticks.'
    );
  });

  it('recommends creating a custom universe before focused replay when only the example exists', async () => {
    const { sessionsDir, dir } = await writeSessionFixture(baseSession);
    const examplePath = join(dir, 'tradeableUniverse.example.json');
    await writeFile(examplePath, JSON.stringify(exampleUniverse), 'utf8');

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig([
        '--sessions-dir',
        sessionsDir,
        '--universe',
        join(dir, 'missing-custom.json'),
        '--example-universe',
        examplePath
      ])
    );

    expect(summary.recommendation).toBe(
      'Create config/tradeableUniverse.json from the example before focused replay research.'
    );
  });

  it('recommends replaying the latest session with a custom universe when usable snapshots exist', async () => {
    const { sessionsDir, dir } = await writeSessionFixture(baseSession);
    const customPath = join(dir, 'tradeableUniverse.json');
    await writeFile(customPath, JSON.stringify(exampleUniverse), 'utf8');

    const summary = await runSentinelDashboard(
      createSentinelDashboardConfig(['--sessions-dir', sessionsDir, '--universe', customPath])
    );

    expect(summary.recommendation).toContain('Replay the latest session with --universe');
  });

  it('supports machine-readable JSON output from the command formatter path', async () => {
    const { sessionsDir } = await writeSessionFixture(baseSession);
    const config = createSentinelDashboardConfig([
      '--sessions-dir',
      sessionsDir,
      '--example-universe',
      'config/tradeableUniverse.example.json',
      '--json'
    ]);
    const summary = await runSentinelDashboard(config);
    const parsed = JSON.parse(JSON.stringify(summary));

    expect(config.json).toBe(true);
    expect(parsed.safety.autoTrading).toBe('disabled');
    expect(parsed.latestSession.sessionId).toBe('atrad-session-base');
  });

  it('does not introduce live services, credentials, or order action code', async () => {
    const source = await readFile('scripts/sentinelDashboard.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/chromium|firefox|webkit/i);
    expect(source).not.toMatch(/new SentinelPipeline|runManualTelegramTest|runManualSupabaseTest/);
    expect(source).not.toMatch(/placeOrder|submit|confirm|market order|limit order/i);
  });
});

async function writeSessionFixture(session: typeof baseSession): Promise<{ dir: string; sessionsDir: string; path: string }> {
  const dir = await mkdtemp(join(tmpdir(), 'sentinel-dashboard-'));
  const sessionsDir = join(dir, 'sessions');
  const path = join(sessionsDir, 'atrad-session.json');
  await mkdir(sessionsDir);
  await writeFile(path, JSON.stringify(session), 'utf8');
  return { dir, sessionsDir, path };
}

function snapshot(ticker: string, timestamp: number): Record<string, unknown> {
  return {
    ticker,
    timestamp,
    lastPrice: 10,
    bestBid: 9.9,
    bestAsk: 10,
    bidDepth: 1000,
    askDepth: 800,
    volume: 1000,
    totalTurnover: 10000,
    source: 'atrad-market-watch'
  };
}

function diagnostic(marketState: string): Record<string, unknown> {
  return {
    tickNumber: 1,
    capturedAt: '2026-05-08T10:15:00.000Z',
    marketState,
    rawRowsExtracted: 2,
    acceptedSnapshots: 1,
    usableSnapshots: 1,
    quarantinedSnapshots: 0,
    rejectedSnapshots: 0
  };
}
