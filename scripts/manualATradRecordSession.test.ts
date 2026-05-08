import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DEFAULT_ATRAD_BASE_URL } from './manualATradLogin.js';
import {
  buildATradRecordSessionOutputPath,
  createManualATradRecordSessionConfig,
  formatManualATradRecordSessionInstructions,
  runManualATradRecordSession,
  type ManualATradRecordSessionRuntime
} from './manualATradRecordSession.js';

const highConfidenceRow = {
  Security: 'HIGH.N0000',
  'Company Name': 'High Confidence PLC',
  'Bid Qty': '1,000',
  'Bid Price': '54.50',
  'Ask Price': '55.00',
  'Ask Qty': '800',
  Last: '54.90',
  'Last Qty': '100',
  Change: '0.40',
  High: '55.20',
  Low: '54.40',
  VWA: '54.80',
  Volume: '12,500',
  Turnover: '686,250',
  Trades: '42',
  'Price Close': '54.50',
  'Buy Sentiment': '62%',
  Time: '10:35:00'
};

const mediumConfidenceRow = {
  Security: 'MEDM.N0000',
  'Company Name': 'Medium Confidence PLC',
  'Bid Qty': '900',
  'Bid Price': '31.00',
  'Ask Price': '31.20',
  'Ask Qty': '700',
  Last: '31.10',
  'Last Qty': '50',
  Change: '0.10',
  High: '31.30',
  Low: '30.90',
  Volume: '8,400',
  Turnover: '261,240',
  Trades: '23',
  'Price Close': '34.23%'
};

const rejectedRow = {
  Security: 'REJT.N0000',
  'Company Name': 'Rejected PLC',
  'Bid Qty': '500',
  'Bid Price': '10.00',
  'Ask Price': '20.00',
  'Ask Qty': '400',
  Last: '10.10',
  Volume: '5,000',
  Turnover: '50,500'
};

describe('manual ATrad record-session helpers', () => {
  it('parses recorder CLI flags', () => {
    const config = createManualATradRecordSessionConfig(
      [
        '--base-url',
        'https://example.com/watch',
        '--duration-seconds',
        '90',
        '--interval-seconds',
        '5',
        '--output',
        'data/custom',
        '--allow-medium-confidence',
        '--include-quarantined',
        '--max-ticks',
        '3'
      ],
      1_700_000_000_000
    );

    expect(config).toEqual({
      baseUrl: 'https://example.com/watch',
      durationSeconds: 90,
      intervalSeconds: 5,
      outputPath: 'data/custom/atrad-session-20231114-221320.json',
      allowMediumConfidence: true,
      includeQuarantined: true,
      maxTicks: 3,
      headless: false,
      readonlyMode: true
    });
  });

  it('builds a default ignored output path', () => {
    const outputPath = buildATradRecordSessionOutputPath(1_700_000_000_000);

    expect(outputPath).toBe('data/live-sessions/atrad-session-20231114-221320.json');
  });

  it('prints manual recording instructions', () => {
    const instructions = formatManualATradRecordSessionInstructions(
      createManualATradRecordSessionConfig([], 1_700_000_000_000)
    );

    expect(instructions.join('\n')).toContain('Full Watch - Equity');
    expect(instructions.join('\n')).toContain('read-only');
    expect(instructions.join('\n')).toContain('data/live-sessions');
  });

  it('records only usable snapshots by default while looping for max ticks', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(['--max-ticks', '2'], runtime.now()),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.session.totals.ticksAttempted).toBe(2);
    expect(result.session.totals.rawRowsExtracted).toBe(6);
    expect(result.session.totals.usableSnapshots).toBe(2);
    expect(result.session.totals.quarantinedSnapshots).toBe(2);
    expect(result.session.totals.rejectedSnapshots).toBe(2);
    expect(result.session.snapshots).toHaveLength(2);
    expect(result.session.snapshots.every((snapshot) => snapshot.ticker === 'HIGH.N0000')).toBe(true);
    expect(result.session.diagnostics).toHaveLength(2);
    expect(runtime.calls).toContain('wait');
    expect(runtime.calls).toContain('sleep:15000');
  });

  it('includes quarantined rows only in the optional quarantine section', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--max-ticks', '1', '--include-quarantined'],
        runtime.now()
      ),
      runtime
    );

    expect(result.session.snapshots).toHaveLength(1);
    expect(result.session.quarantinedRows).toEqual([
      {
        tickNumber: 1,
        ticker: 'MEDM.N0000',
        status: 'MEDIUM_CONFIDENCE',
        issueCodes: ['TRAILING_FIELDS_SHIFTED']
      }
    ]);
  });

  it('allows medium confidence rows when explicitly configured', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--max-ticks', '1', '--allow-medium-confidence'],
        runtime.now()
      ),
      runtime
    );

    expect(result.session.confidencePolicy).toBe('HIGH_CONFIDENCE + MEDIUM_CONFIDENCE');
    expect(result.session.totals.usableSnapshots).toBe(2);
    expect(result.session.totals.quarantinedSnapshots).toBe(0);
    expect(result.session.snapshots.map((snapshot) => snapshot.ticker)).toEqual(['HIGH.N0000', 'MEDM.N0000']);
  });

  it('writes a clean session JSON structure without credentials or session tokens', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(['--max-ticks', '1'], runtime.now()),
      runtime
    );

    expect(result.session).toMatchObject({
      sessionId: 'atrad-session-20231114-221320',
      source: 'atrad-full-watch-equity',
      mode: 'read-only-local-recording',
      confidencePolicy: 'HIGH_CONFIDENCE only',
      intervalSeconds: 15,
      durationSeconds: 60
    });

    expect(runtime.writes).toHaveLength(1);
    expect(runtime.writes[0]?.path).toBe('data/live-sessions/atrad-session-20231114-221320.json');
    expect(runtime.writes[0]?.contents).toContain('"sessionId": "atrad-session-20231114-221320"');
    expect(runtime.writes[0]?.contents).not.toMatch(/cookie|storageState|session=|token|password|otp/i);
  });

  it('does not read credentials, environment variables, or include order action strings', () => {
    const source = readFileSync('scripts/manualATradRecordSession.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/\busername\b|\bpassword\b|\botp\b/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|quantity|price input|market order|limit order/i);
    expect(source).not.toMatch(/click\(|fill\(|type\(/);
  });
});

function createFakeRuntime(): ManualATradRecordSessionRuntime & {
  calls: string[];
  writes: Array<{ path: string; contents: string }>;
} {
  let now = 1_700_000_000_000;
  const calls: string[] = [];
  const writes: Array<{ path: string; contents: string }> = [];

  return {
    calls,
    writes,
    async launchSession() {
      calls.push('launch-session');
      return {
        session: {
          pages() {
            return [createFakePage(calls)];
          },
          async newPage() {
            calls.push('new-page');
            return createFakePage(calls);
          }
        },
        async close() {
          calls.push('close');
        }
      };
    },
    async waitForUser() {
      calls.push('wait');
    },
    now() {
      return now;
    },
    async sleep(ms: number) {
      calls.push(`sleep:${ms}`);
      now += ms;
    },
    async ensureDir(path: string) {
      calls.push(`mkdir:${path.replace(/\\/g, '/')}`);
    },
    async writeFile(path: string, contents: string) {
      writes.push({ path: path.replace(/\\/g, '/'), contents });
      calls.push(`write:${path.replace(/\\/g, '/')}`);
    },
    log(message: string) {
      calls.push(`log:${message}`);
    }
  };
}

function createFakePage(calls: string[]) {
  const headers = Object.keys(highConfidenceRow);
  const asRowCells = (row: Record<string, string>) => headers.map((header) => row[header] ?? '');

  return {
    url() {
      return 'https://atrad.example.com/watch';
    },
    async title() {
      return 'ATrad Market Watch';
    },
    frames() {
      return [this];
    },
    async goto(target: string, _options: { waitUntil: 'domcontentloaded'; timeout: number }) {
      calls.push(`goto:${target}`);
    },
    async evaluate(pageFunction: string | (() => unknown)) {
      calls.push(`evaluate:${typeof pageFunction}`);
      if (typeof pageFunction !== 'string') {
        return [];
      }

      if (pageFunction.includes('const allowedHeaders =')) {
        return {
          chosenCandidateIndex: 0,
          candidates: [
            {
              kind: 'table',
              score: 90,
              headerRowIndex: 0,
              headerCells: headers,
              containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
              rows: [
                asRowCells(highConfidenceRow),
                asRowCells(mediumConfidenceRow),
                asRowCells(rejectedRow)
              ]
            }
          ],
          dojoCandidates: [],
          broadScan: undefined,
          headerMatches: []
        };
      }

      return [];
    }
  };
}
