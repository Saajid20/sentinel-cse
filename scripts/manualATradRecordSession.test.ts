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

const placeholderRow = {
  Security: 'IDLE.N0000',
  'Company Name': 'Inactive PLC',
  'Bid Qty': '-',
  'Bid Price': '-',
  'Ask Price': '-',
  'Ask Qty': '-',
  Last: '-',
  'Last Qty': '-',
  Change: '-',
  High: '0.00',
  Low: '0.00',
  VWA: '0.00',
  Volume: '0',
  Turnover: '-',
  Trades: '-',
  'Price Close': '0.00',
  'Buy Sentiment': '-',
  Time: '--:--:--'
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
      readinessRetries: 3,
      readinessWaitSeconds: 3,
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
    expect(instructions.join('\n')).toContain('Readiness retries: 3');
  });

  it('records only usable snapshots by default while looping for max ticks', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(['--max-ticks', '3', '--duration-seconds', '60'], runtime.now()),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.session.totals.ticksAttempted).toBe(3);
    expect(result.session.totals.rawRowsExtracted).toBe(9);
    expect(result.session.totals.usableSnapshots).toBe(3);
    expect(result.session.totals.quarantinedSnapshots).toBe(3);
    expect(result.session.totals.rejectedSnapshots).toBe(3);
    expect(result.session.snapshots).toHaveLength(3);
    expect(result.session.snapshots.every((snapshot) => snapshot.ticker === 'HIGH.N0000')).toBe(true);
    expect(result.session.diagnostics).toHaveLength(3);
    expect(runtime.calls).toContain('wait');
    expect(runtime.calls.filter((call) => call === 'sleep:15000')).toHaveLength(2);
    expect(runtime.calls).toContain('log:ATrad Market Watch ready: rawRows=3, headers=yes');
    expect(runtime.calls).toContain('log:Tick 1: usable=1, quarantined=1, rejected=1, placeholders=0');
    expect(runtime.calls).toContain('log:Tick 2: usable=1, quarantined=1, rejected=1, placeholders=0');
    expect(runtime.calls).toContain('log:Tick 3: usable=1, quarantined=1, rejected=1, placeholders=0');
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

  it('tracks placeholder rows and does not record them as usable snapshots', async () => {
    const runtime = createFakeRuntime({ includePlaceholderRow: true });
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(['--max-ticks', '1'], runtime.now()),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.session.totals.ticksAttempted).toBe(1);
    expect(result.session.totals.rawRowsExtracted).toBe(4);
    expect(result.session.totals.usableSnapshots).toBe(1);
    expect(result.session.snapshots.map((snapshot) => snapshot.ticker)).toEqual(['HIGH.N0000']);
    expect(result.session.diagnostics[0]).toMatchObject({
      placeholderRows: 1,
      inactiveRows: 1,
      zeroVolumeRows: 1
    });
    expect(runtime.calls).toContain(
      'log:Tick 1: usable=1, quarantined=1, rejected=2, placeholders=1'
    );
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

  it('stops on duration before reaching the max tick limit', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--max-ticks', '5', '--duration-seconds', '25', '--interval-seconds', '10'],
        runtime.now()
      ),
      runtime
    );

    expect(result.session.totals.ticksAttempted).toBe(3);
    expect(runtime.calls.filter((call) => call === 'sleep:10000')).toHaveLength(2);
  });

  it('honors duration-only recording with interval spacing and no final wait', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--duration-seconds', '30', '--interval-seconds', '10'],
        runtime.now()
      ),
      runtime
    );

    expect(result.session.totals.ticksAttempted).toBe(3);
    expect(runtime.calls.filter((call) => call === 'sleep:10000')).toHaveLength(2);
  });

  it('waits and retries readiness without counting ticks', async () => {
    const runtime = createFakeRuntime({ readinessSequence: ['not-ready', 'ready'] });
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--max-ticks', '2', '--readiness-wait-seconds', '2'],
        runtime.now()
      ),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.session.totals.ticksAttempted).toBe(2);
    expect(runtime.calls.filter((call) => call === 'wait')).toHaveLength(2);
    expect(runtime.calls.filter((call) => call === 'sleep:2000')).toHaveLength(1);
    expect(runtime.calls).toContain(
      'log:ATrad Market Watch is not ready yet. Finish login, select Full Watch - Equity, then press Enter again.'
    );
  });

  it('fails cleanly when readiness never passes and does not write a session file', async () => {
    const runtime = createFakeRuntime({ readinessSequence: ['not-ready', 'not-ready', 'not-ready'] });
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(
        ['--readiness-retries', '2', '--readiness-wait-seconds', '1'],
        runtime.now()
      ),
      runtime
    );

    expect(result.ok).toBe(false);
    expect(result.message).toContain('not ready');
    expect(result.session.totals.ticksAttempted).toBe(0);
    expect(runtime.writes).toHaveLength(0);
    expect(runtime.calls.filter((call) => call === 'sleep:1000')).toHaveLength(2);
  });

  it('writes a clean session JSON structure without credentials or session tokens', async () => {
    const runtime = createFakeRuntime();
    const result = await runManualATradRecordSession(
      createManualATradRecordSessionConfig(['--max-ticks', '1'], runtime.now()),
      runtime
    );

    expect(result.session).toMatchObject({
      sessionId: 'atrad-session-20231114-221405',
      source: 'atrad-full-watch-equity',
      mode: 'read-only-local-recording',
      confidencePolicy: 'HIGH_CONFIDENCE only',
      intervalSeconds: 15,
      durationSeconds: 60
    });

    expect(runtime.writes).toHaveLength(1);
    expect(runtime.writes[0]?.path).toBe('data/live-sessions/atrad-session-20231114-221320.json');
    expect(runtime.writes[0]?.contents).toContain('"sessionId": "atrad-session-20231114-221405"');
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

function createFakeRuntime(options: {
  readinessSequence?: Array<'ready' | 'not-ready'>;
  includePlaceholderRow?: boolean;
} = {}): ManualATradRecordSessionRuntime & {
  calls: string[];
  writes: Array<{ path: string; contents: string }>;
} {
  let now = 1_700_000_000_000;
  const calls: string[] = [];
  const writes: Array<{ path: string; contents: string }> = [];
  const readinessSequence = options.readinessSequence ?? ['ready'];
  let extractionAttempt = 0;

  return {
    calls,
    writes,
    async launchSession() {
      calls.push('launch-session');
      return {
        session: {
          pages() {
            return [
              createFakePage(
                calls,
                readinessSequence,
                () => extractionAttempt,
                () => { extractionAttempt += 1; },
                options.includePlaceholderRow === true
              )
            ];
          },
          async newPage() {
            calls.push('new-page');
            return createFakePage(
              calls,
              readinessSequence,
              () => extractionAttempt,
              () => { extractionAttempt += 1; },
              options.includePlaceholderRow === true
            );
          }
        },
        async close() {
          calls.push('close');
        }
      };
    },
    async waitForUser() {
      calls.push('wait');
      now += 45_000;
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

function createFakePage(
  calls: string[],
  readinessSequence: Array<'ready' | 'not-ready'>,
  getExtractionAttempt: () => number,
  incrementExtractionAttempt: () => void,
  includePlaceholderRow: boolean
) {
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
        const readinessState = readinessSequence[
          Math.min(getExtractionAttempt(), readinessSequence.length - 1)
        ] ?? 'ready';
        incrementExtractionAttempt();

        if (readinessState === 'not-ready') {
          return {
            chosenCandidateIndex: -1,
            candidates: [],
            dojoCandidates: [],
            broadScan: undefined,
            headerMatches: []
          };
        }

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
                asRowCells(rejectedRow),
                ...(includePlaceholderRow ? [asRowCells(placeholderRow)] : [])
              ]
            }
          ],
          dojoCandidates: [],
          broadScan: undefined,
          headerMatches: []
        };
      }

      if (pageFunction.includes("querySelectorAll('iframe').length")) {
        return 0;
      }

      const diagnosticState = readinessSequence[
        Math.max(0, Math.min(getExtractionAttempt() - 1, readinessSequence.length - 1))
      ] ?? 'ready';
      if (diagnosticState === 'not-ready') {
        return {
          tableCount: 0,
          rowCount: 0,
          visibleTextCount: 2,
          firstVisibleTextSnippets: ['ATrad Login', 'Sign in'],
          keywordMatches: []
        };
      }

      return {
        tableCount: 1,
        rowCount: 0,
        visibleTextCount: 5,
        firstVisibleTextSnippets: ['Market Watch', 'Full Watch', 'Equity', 'Security', 'Volume'],
        keywordMatches: ['Market Watch', 'Security', 'Bid', 'Ask', 'Last', 'Volume']
      };
    }
  };
}
