import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  buildDashboardApiResponse,
  buildDashboardCommandSnippets,
  createDashboardServerConfig,
  startDashboardServer,
  type DashboardServerHandle
} from './dashboardServer.js';

const handles: DashboardServerHandle[] = [];

const fakeSession = {
  sessionId: 'atrad-session-web',
  startedAt: '2026-05-08T10:15:00.000Z',
  endedAt: '2026-05-08T10:16:00.000Z',
  source: 'atrad-full-watch-equity',
  mode: 'read-only-local-recording',
  confidencePolicy: 'HIGH_CONFIDENCE only',
  intervalSeconds: 10,
  durationSeconds: 60,
  totals: {
    ticksAttempted: 2,
    rawRowsExtracted: 4,
    usableSnapshots: 2,
    quarantinedSnapshots: 0,
    rejectedSnapshots: 1
  },
  snapshots: [
    snapshot('ALFA.N0000', 1_715_160_000_000),
    snapshot('ALFA.N0000', 1_715_160_010_000)
  ],
  diagnostics: [
    { marketState: 'OPEN' },
    { marketState: 'OPEN' }
  ]
};

const fakeUniverse = {
  name: 'web-universe',
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
};

afterEach(async () => {
  await Promise.all(
    handles.splice(0).map(
      (handle) =>
        new Promise<void>((resolve, reject) => {
          handle.server.close((error) => (error ? reject(error) : resolve()));
        })
    )
  );
});

describe('dashboard web server', () => {
  it('returns the dashboard HTML page', async () => {
    const handle = await startDashboardServer({
      ...createDashboardServerConfig([]),
      port: 0
    });
    handles.push(handle);

    const response = await fetch(handle.url);
    const html = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toContain('text/html');
    expect(html).toContain('Operator Console');
    expect(html).toContain('READ-ONLY MODE');
    expect(html).toContain('Useful Local Commands');
  });

  it('returns dashboard JSON from /api/dashboard', async () => {
    const fixture = await writeDashboardFixture();
    const handle = await startDashboardServer({
      ...createDashboardServerConfig([
        '--sessions-dir',
        fixture.sessionsDir,
        '--universe',
        fixture.universePath
      ]),
      port: 0
    });
    handles.push(handle);

    const response = await fetch(`${handle.url}/api/dashboard`);
    const json = await response.json();

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toContain('application/json');
    expect(json.latestSession.sessionId).toBe('atrad-session-web');
    expect(json.tradeableUniverse.name).toBe('web-universe');
    expect(json.commandSnippets).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ command: expect.stringContaining('pnpm sentinel dashboard') })
      ])
    );
  });

  it('does not expose secret-shaped fields in the JSON response', async () => {
    const fixture = await writeDashboardFixture();
    const response = await buildDashboardApiResponse(
      {
        ...createDashboardServerConfig([
          '--sessions-dir',
          fixture.sessionsDir,
          '--universe',
          fixture.universePath
        ]),
        port: 0
      }
    );
    const text = JSON.stringify(response).toLowerCase();

    expect(text).not.toContain('password');
    expect(text).not.toContain('cookie');
    expect(text).not.toContain('token');
    expect(text).not.toContain('storage state');
    expect(text).not.toContain('.env');
  });

  it('uses the local read-only dashboard summary logic', async () => {
    const fixture = await writeDashboardFixture();
    const response = await buildDashboardApiResponse({
      ...createDashboardServerConfig([
        '--sessions-dir',
        fixture.sessionsDir,
        '--universe',
        fixture.universePath
      ]),
      port: 0
    });

    expect(response.safety.liveSentinelPipelineFromATrad).toBe('disabled');
    expect(response.localFiles.sessionFileCount).toBe(1);
    expect(response.latestSession?.replayReadiness.likelyUsefulForReplay).toBe(true);
    expect(response.recommendation).toContain('Replay the latest session');
  });

  it('builds command snippets as display-only text', () => {
    const snippets = buildDashboardCommandSnippets({
      safety: {
        atradMode: 'read-only/manual',
        autoTrading: 'disabled',
        orderPlacement: 'disabled',
        telegramLiveAlerts: 'disabled',
        supabaseLiveWrites: 'disabled',
        liveSentinelPipelineFromATrad: 'disabled'
      },
      localFiles: {
        sessionsDir: 'data/live-sessions',
        exists: true,
        sessionFileCount: 1,
        latestSessionFilePath: 'data/live-sessions/latest.json',
        gitIgnoredWarning: 'ignored'
      },
      tradeableUniverse: {
        path: 'config/tradeableUniverse.json',
        source: 'custom',
        name: 'web-universe'
      },
      recommendation: 'Replay the latest session.'
    });

    expect(snippets.map((snippet) => snippet.command)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('pnpm atrad:record-session'),
        expect.stringContaining('pnpm atrad:replay-session'),
        expect.stringContaining('pnpm universe:validate'),
        'pnpm sentinel dashboard'
      ])
    );
    expect(snippets.map((snippet) => snippet.command).join('\n')).not.toMatch(/curl|fetch|POST|onclick/i);
  });
});

async function writeDashboardFixture(): Promise<{ dir: string; sessionsDir: string; universePath: string }> {
  const dir = await mkdtemp(join(tmpdir(), 'sentinel-web-dashboard-'));
  const sessionsDir = join(dir, 'sessions');
  const universePath = join(dir, 'tradeableUniverse.json');
  await mkdir(sessionsDir);
  await writeFile(join(sessionsDir, 'atrad-session-web.json'), JSON.stringify(fakeSession), 'utf8');
  await writeFile(universePath, JSON.stringify(fakeUniverse), 'utf8');
  return { dir, sessionsDir, universePath };
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
