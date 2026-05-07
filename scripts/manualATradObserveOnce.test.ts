import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import { MarketDataSanitizer } from '../packages/core/src/index.js';
import { ATRAD_PERSISTENT_PROFILE_PATH, ATRAD_STORAGE_STATE_PATH } from './manualATradLogin.js';
import {
  buildMarketWatchRowFromCells,
  collectPageDiagnostics,
  createManualATradObserveOnceConfig,
  DEFAULT_ATRAD_MARKET_WATCH_URL,
  extractVisibleMarketWatchRows,
  formatObserveOnceSummary,
  ManualATradObserveOnceRuntime,
  marketWatchRowToRawSnapshot,
  sanitizeMarketWatchRows,
  runManualATradObserveOnce
} from './manualATradObserveOnce.js';

const fakeMarketWatchRow = {
  Security: 'SAMP.N0000',
  'Company Name': 'Sample Holdings PLC',
  'Bid Qty': '1,000',
  'Bid Price': '54.50',
  'Ask Price': '55.00',
  'Ask Qty': '800',
  Last: '55.00',
  'Last Qty': '100',
  Change: '1.00',
  '% Change': '1.85',
  High: '56.00',
  Low: '53.00',
  VWA: '54.20',
  Volume: '12,500',
  Turnover: '687,500',
  Trades: '42',
  'Price Close': '54.00',
  'Buy Sentiment': '62%',
  Time: '10:35:00'
};

describe('manual ATrad observe-once helpers', () => {
  it('parses the diagnose flag from CLI args', () => {
    const config = createManualATradObserveOnceConfig(['--base-url', 'https://example.com/watch', '--diagnose']);

    expect(config.baseUrl).toBe('https://example.com/watch');
    expect(config.diagnose).toBe(true);
    expect(config.readonlyMode).toBe(true);
  });

  it('parses the persistent profile flag from CLI args', () => {
    const config = createManualATradObserveOnceConfig(['--persistent-profile']);

    expect(config.persistentProfile).toBe(true);
    expect(config.persistentProfilePath).toBe(ATRAD_PERSISTENT_PROFILE_PATH);
  });

  it('parses the debug rows flag from CLI args', () => {
    const config = createManualATradObserveOnceConfig(['--debug-rows']);

    expect(config.debugRows).toBe(true);
  });

  it('returns a helpful result when storage state is missing', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: false,
      calls
    });

    const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(), runtime);

    expect(result.ok).toBe(false);
    expect(result.message).toContain('Run pnpm atrad:login first');
    expect(calls).not.toContain('launch');
  });

  it('returns a helpful message when a persistent profile is redirected to login', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls,
      pageUrl: 'https://online.fge.lk/atsweb/login'
    });

    const result = await runManualATradObserveOnce(
      createManualATradObserveOnceConfig(['--persistent-profile']),
      runtime
    );

    expect(result.ok).toBe(false);
    expect(result.message).toContain('Persistent ATrad session not authenticated');
    expect(result.message).toContain('--persistent-profile first');
    expect(calls).toContain('launch-persistent');
  });

  it('maps a Market Watch row to a RawMarketSnapshot', () => {
    const rawSnapshot = marketWatchRowToRawSnapshot(fakeMarketWatchRow, 1_000);

    expect(rawSnapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      lastPrice: '55.00',
      bestBid: '54.50',
      bestAsk: '55.00',
      bidDepth: '1000',
      askDepth: '800',
      volume: '12500',
      totalTurnover: '687500',
      timestamp: 1_000,
      source: 'atrad-market-watch'
    });
    expect(rawSnapshot.metadata).toMatchObject({
      companyName: 'Sample Holdings PLC',
      high: '56.00',
      low: '53.00',
      vwa: '54.20',
      turnover: '687500',
      trades: '42',
      priceClose: '54.00',
      buySentiment: '62%',
      rawRow: fakeMarketWatchRow
    });
  });

  it('handles comma-separated values and symbols in Full Watch numeric fields', () => {
    const rawSnapshot = marketWatchRowToRawSnapshot(
      {
        ...fakeMarketWatchRow,
        'Bid Qty': '1,250 ▲',
        'Bid Price': '54.50 ▲',
        'Ask Price': '55.00 ▼',
        Last: '55.25 ▲',
        Volume: '12,500',
        Turnover: '687,500'
      },
      1_000
    );

    expect(rawSnapshot).toMatchObject({
      bidDepth: '1250',
      bestBid: '54.50',
      bestAsk: '55.00',
      lastPrice: '55.25',
      volume: '12500',
      totalTurnover: '687500'
    });
  });

  it('builds a Full Watch row from headers and cells with an action-icon column', () => {
    const row = buildMarketWatchRowFromCells(
      [
        '',
        'Security',
        'Company Name',
        'Bid Qty',
        'Bid Price',
        'Ask Price',
        'Ask Qty',
        'Last',
        'Volume',
        'Turnover',
        'Buy Sentiment',
        'Time'
      ],
      [
        '>',
        'SAMP.N0000',
        'Sample Holdings PLC',
        '1,000',
        '54.50',
        '55.00',
        '800',
        '55.00',
        '12,500',
        '687,500',
        '62%',
        '10:35:00'
      ]
    );

    expect(row).toMatchObject({
      Security: 'SAMP.N0000',
      'Company Name': 'Sample Holdings PLC',
      'Bid Qty': '1,000',
      'Bid Price': '54.50',
      'Ask Price': '55.00',
      'Ask Qty': '800',
      Last: '55.00',
      Volume: '12,500',
      Turnover: '687,500',
      'Buy Sentiment': '62%',
      Time: '10:35:00'
    });
  });

  it('sanitizes numeric strings with commas from Market Watch rows', () => {
    const sanitizer = new MarketDataSanitizer();

    const result = sanitizeMarketWatchRows([fakeMarketWatchRow], 1_000, sanitizer);

    expect(result.accepted).toHaveLength(1);
    expect(result.rejected).toHaveLength(0);
    expect(result.accepted[0]?.snapshot).toMatchObject({
      ticker: 'SAMP.N0000',
      bidDepth: 1_000,
      volume: 12_500,
      totalTurnover: 687_500
    });
  });

  it('rejects unsafe action descriptions through the read-only guard', () => {
    expect(() => assertATradReadOnlySafety('read Market Watch table data')).not.toThrow();
    expect(() => assertATradReadOnlySafety('click buy order submit control')).toThrow(
      /Unsafe ATrad read-only action/
    );
  });

  it('extracts rows through an injected fake page without a real browser', async () => {
    let evaluateInput: string | (() => unknown) | undefined;
    const rows = await extractVisibleMarketWatchRows({
      async goto() {
        throw new Error('goto should not be called by extractor');
      },
      async evaluate(pageFunction) {
        evaluateInput = pageFunction;
        return {
          chosenCandidateIndex: 0,
          candidates: [
            {
              score: 80,
              headerRowIndex: 0,
              headerCells: Object.keys(fakeMarketWatchRow),
              containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
              rows: [Object.values(fakeMarketWatchRow)]
            }
          ]
        };
      }
    });

    expect(rows).toEqual([fakeMarketWatchRow]);
    expect(typeof evaluateInput).toBe('string');
    expect(String(evaluateInput)).not.toContain('__name');
  });

  it('runs observe-once with an injected fake browser runtime', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls
    });

    const result = await runManualATradObserveOnce(createManualATradObserveOnceConfig(), runtime);

    expect(result.ok).toBe(true);
    expect(result.rawRows).toEqual([fakeMarketWatchRow]);
    expect(result.accepted).toHaveLength(1);
    expect(calls).toEqual(
      expect.arrayContaining([
        'launch-storage',
        `context:${ATRAD_STORAGE_STATE_PATH}`,
        'new-page',
        `goto:${new URL(DEFAULT_ATRAD_MARKET_WATCH_URL).toString()}`,
        'close'
      ])
    );
  });

  it('uses the persistent profile runtime when the flag is present', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls,
      pageUrl: 'https://atrad.example.com/watch'
    });

    const result = await runManualATradObserveOnce(
      createManualATradObserveOnceConfig(['--persistent-profile']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(calls).toEqual(
      expect.arrayContaining([
        'launch-persistent',
        `goto:${new URL(DEFAULT_ATRAD_MARKET_WATCH_URL).toString()}`,
        'close'
      ])
    );
    expect(calls).not.toContain(`context:${ATRAD_STORAGE_STATE_PATH}`);
  });

  it('runs read-only diagnostics across the page and child frames', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls,
      pageUrl: 'https://atrad.example.com/watch?session=secret123#frag',
      pageTitle: 'ATrad Market Watch 123456789',
      pageDiagnostics: {
        tableCount: 2,
        rowCount: 12,
        visibleTextCount: 6,
        firstVisibleTextSnippets: ['Market Watch', 'Security', 'Bid Price', 'Volume 123456'],
        keywordMatches: ['Market Watch', 'Security', 'Bid Price']
      },
      frames: [
        {
          url: 'https://atrad.example.com/frame?token=abcdef1234567890',
          title: 'Child Frame 999999',
          diagnostics: {
            tableCount: 1,
            rowCount: 4,
            visibleTextCount: 2,
            firstVisibleTextSnippets: ['Trades', 'Turnover 777777'],
            keywordMatches: ['Trades', 'Turnover 777777']
          }
        }
      ]
    });

    const result = await runManualATradObserveOnce(
      createManualATradObserveOnceConfig(['--diagnose']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.message).toContain('diagnostics');
    expect(result.rawRows).toEqual([]);
    expect(result.accepted).toEqual([]);
    expect(result.rejected).toEqual([]);
    expect(result.diagnostics).toMatchObject({
      pageUrl: 'https://atrad.example.com/watch',
      pageTitle: 'ATrad Market Watch [redacted-number]',
      frameCount: 2,
      iframeCount: 1
    });
    expect(result.diagnostics?.page.firstVisibleTextSnippets).toContain('Volume [redacted-number]');
    expect(result.diagnostics?.frames[0]).toMatchObject({
      scope: 'frame-1',
      url: 'https://atrad.example.com/frame',
      title: 'Child Frame [redacted-number]'
    });
    expect(calls).toEqual(
      expect.arrayContaining([
        'frame-evaluate:main:string',
        'frame-evaluate:frame-1:string',
        'page-evaluate:iframe-count'
      ])
    );
  });

  it('runs read-only row debug with candidate counts, headers, sample rows, and rejection reasons', async () => {
    const calls: string[] = [];
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls,
      extractionCandidates: {
        chosenCandidateIndex: 0,
        candidates: [
          {
            score: 87,
            headerRowIndex: 0,
            headerCells: [
              'Security',
              'Bid Qty',
              'Bid Price',
              'Ask Price',
              'Ask Qty',
              'Last',
              'Volume',
              'Turnover'
            ],
            containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
            rows: [
              ['SAMP.N0000', '1,000', '54.50', '55.00', '800', '55.00', '12,500', '687,500'],
              ['', '', '', '', '', '', '', ''],
              ['TOTAL', '', '', '', '', '', '', '']
            ]
          }
        ]
      }
    });

    const result = await runManualATradObserveOnce(
      createManualATradObserveOnceConfig(['--debug-rows']),
      runtime
    );
    const lines = formatObserveOnceSummary(result).join('\n');

    expect(result.ok).toBe(true);
    expect(result.extractionDebug?.candidateCount).toBe(1);
    expect(result.extractionDebug?.chosenCandidate?.headerCells).toEqual([
      'Security',
      'Bid Qty',
      'Bid Price',
      'Ask Price',
      'Ask Qty',
      'Last',
      'Volume',
      'Turnover'
    ]);
    expect(result.extractionDebug?.chosenCandidate?.rowAnalyses[0]?.accepted).toBe(true);
    expect(result.extractionDebug?.chosenCandidate?.rowAnalyses[1]?.reasons).toContain('missing ticker');
    expect(lines).toContain('Candidate Market Watch tables/sections found: 1');
    expect(lines).toContain('Chosen header row cells:');
    expect(lines).toContain('First 10 visible data row cell arrays:');
    expect(lines).toContain('row looked like header/summary');
  });

  it('runs broad debug fallback and header text search when candidate count is zero', async () => {
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls: [],
      extractionCandidates: {
        chosenCandidateIndex: -1,
        candidates: [],
        broadScan: {
          visibleTableCount: 3,
          visibleTrCount: 9,
          visibleRoleGridCount: 1,
          visibleRoleTableCount: 0,
          visibleRoleRowCount: 4,
          tableSummaries: [
            {
              index: 0,
              nearbyTextSnippet: 'Market Watch - Full Watch - Equity',
              rowCount: 3,
              firstRows: [
                ['Security', 'Bid Qty', 'Bid Price'],
                ['SAMP.N0000', '1,000', '54.50']
              ],
              keywordMatches: ['Security', 'Bid', 'Volume']
            }
          ],
          gridSummaries: [
            {
              index: 0,
              typeHint: 'div.grid.market-watch',
              nearbyTextSnippet: 'Security Bid Qty Ask Qty Last Volume',
              childTextChunks: ['Security', 'Bid Qty', 'Last'],
              keywordMatches: ['Security', 'Bid', 'Last', 'Volume']
            }
          ]
        },
        headerMatches: [
          {
            text: 'Security',
            tagName: 'span',
            role: '',
            className: 'market-header',
            ancestorTextSnippet: 'Market Watch Security Bid Qty Last',
            ancestorTagChain: 'span>div>section'
          }
        ]
      }
    });

    const result = await runManualATradObserveOnce(
      createManualATradObserveOnceConfig(['--debug-rows']),
      runtime
    );
    const lines = formatObserveOnceSummary(result).join('\n');

    expect(result.ok).toBe(true);
    expect(result.extractionDebug?.candidateCount).toBe(0);
    expect(lines).toContain('Broad visible table/grid scan');
    expect(lines).toContain('Visible table count: 3');
    expect(lines).toContain('Row 1: ["Security","Bid Qty","Bid Price"]');
    expect(lines).toContain('Header text search fallback');
    expect(lines).toContain('Header 1: Security [span]');
  });

  it('collects diagnostics through injected read-only page inspection helpers', async () => {
    const diagnostics = await collectPageDiagnostics(
      createFakePage({
        calls: [],
        pageUrl: 'https://atrad.example.com/watch?auth=secret',
        pageTitle: 'Overview 123456',
        pageDiagnostics: {
          tableCount: 0,
          rowCount: 0,
          visibleTextCount: 1,
          firstVisibleTextSnippets: ['Last 123456'],
          keywordMatches: ['Last 123456']
        }
      })
    );

    expect(diagnostics.pageUrl).toBe('https://atrad.example.com/watch');
    expect(diagnostics.pageTitle).toBe('Overview [redacted-number]');
    expect(diagnostics.page.firstVisibleTextSnippets).toEqual(['Last [redacted-number]']);
  });

  it('does not read credentials, environment variables, or include unsafe action strings', () => {
    const source = readFileSync('scripts/manualATradObserveOnce.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password|otp/i);
    expect(source).not.toMatch(/\bbuy\b(?!\s+sentiment)|sell|submit|confirm|quantity input|price input|market order|limit order/i);
    expect(source).not.toMatch(/click\(|fill\(|type\(/);
  });
});

function fakeRuntime({
  storageStateExists,
  calls,
  pageUrl,
  pageTitle,
  pageDiagnostics,
  frames,
  extractionCandidates
}: {
  storageStateExists: boolean;
  calls: string[];
  pageUrl?: string;
  pageTitle?: string;
  pageDiagnostics?: FrameDiagnosticsPayload;
  frames?: FakeFrameConfig[];
  extractionCandidates?: ExtractionCandidatesPayload;
}): ManualATradObserveOnceRuntime {
  return {
    async storageStateExists() {
      return storageStateExists;
    },
    async launchSession(config) {
      calls.push(config.persistentProfile ? 'launch-persistent' : 'launch-storage');
      if (config.persistentProfile) {
        return {
          session: createFakeSession({
            calls,
            pageUrl,
            pageTitle,
            pageDiagnostics,
            frames,
            extractionCandidates
          }),
          async close() {
            calls.push('close');
          }
        };
      }

      return {
        session: {
          pages() {
            return [];
          },
          async newPage() {
            calls.push('new-page');
            calls.push(`context:${config.storageStatePath}`);
            return createFakePage({
              calls,
              pageUrl,
              pageTitle,
              pageDiagnostics,
              frames,
              extractionCandidates
            });
          }
        },
        async close() {
          calls.push('close');
        }
      };
    },
    now: () => 1_000,
    log: (message) => calls.push(`log:${message}`)
  };
}

interface FrameDiagnosticsPayload {
  tableCount: number;
  rowCount: number;
  visibleTextCount: number;
  firstVisibleTextSnippets: string[];
  keywordMatches: string[];
}

interface FakeFrameConfig {
  url: string;
  title: string;
  diagnostics: FrameDiagnosticsPayload;
}

function createFakePage({
  calls,
  pageUrl,
  pageTitle,
  pageDiagnostics,
  frames,
  extractionCandidates
}: {
  calls: string[];
  pageUrl?: string;
  pageTitle?: string;
  pageDiagnostics?: FrameDiagnosticsPayload;
  frames?: FakeFrameConfig[];
  extractionCandidates?: ExtractionCandidatesPayload;
}) {
  const childFrames = (frames ?? []).map((frame, index) =>
    createFakeFrame({
      calls,
      label: `frame-${index + 1}`,
      url: frame.url,
      title: frame.title,
      diagnostics: frame.diagnostics
    })
  );

  const mainFrame = createFakeFrame({
    calls,
    label: 'main',
    url: pageUrl ?? DEFAULT_ATRAD_MARKET_WATCH_URL,
    title: pageTitle ?? 'ATrad Market Watch',
    diagnostics:
      pageDiagnostics ?? {
        tableCount: 1,
        rowCount: 2,
        visibleTextCount: 3,
        firstVisibleTextSnippets: ['Market Watch', 'Security', 'Volume'],
        keywordMatches: ['Market Watch', 'Security', 'Volume']
      },
    overrides: {
      async goto(url: string) {
        calls.push(`goto:${url}`);
      },
      frames() {
        return [mainFrame, ...childFrames];
      },
      async evaluate(pageFunction: string | (() => unknown)) {
        if (typeof pageFunction === 'string' && pageFunction.includes("querySelectorAll('iframe').length")) {
          calls.push('page-evaluate:iframe-count');
          return childFrames.length;
        }

        calls.push(`frame-evaluate:main:${typeof pageFunction}`);
        if (typeof pageFunction === 'string') {
          if (pageFunction.includes('const allowedHeaders =')) {
            return (
              extractionCandidates ?? {
                chosenCandidateIndex: 0,
                candidates: [
                  {
                    score: 80,
                    headerRowIndex: 0,
                    headerCells: Object.keys(fakeMarketWatchRow),
                    containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
                    rows: [Object.values(fakeMarketWatchRow)]
                  }
                ]
              }
            );
          }

          return (
            pageDiagnostics ?? {
              tableCount: 1,
              rowCount: 2,
              visibleTextCount: 3,
              firstVisibleTextSnippets: ['Market Watch', 'Security', 'Volume'],
              keywordMatches: ['Market Watch', 'Security', 'Volume']
            }
          );
        }

        return [fakeMarketWatchRow];
      }
    }
  });

  return mainFrame;
}

function createFakeSession({
  calls,
  pageUrl,
  pageTitle,
  pageDiagnostics,
  frames,
  extractionCandidates
}: {
  calls: string[];
  pageUrl?: string;
  pageTitle?: string;
  pageDiagnostics?: FrameDiagnosticsPayload;
  frames?: FakeFrameConfig[];
  extractionCandidates?: ExtractionCandidatesPayload;
}) {
  return {
    pages() {
      return [];
    },
    async newPage() {
      calls.push('new-page');
      return createFakePage({
        calls,
        pageUrl,
        pageTitle,
        pageDiagnostics,
        frames,
        extractionCandidates
      });
    }
  };
}

interface ExtractionCandidatesPayload {
  chosenCandidateIndex: number;
  candidates: Array<{
    score: number;
    headerRowIndex: number;
    headerCells: string[];
    containerTextMatches: string[];
    rows: string[][];
  }>;
  broadScan?: {
    visibleTableCount: number;
    visibleTrCount: number;
    visibleRoleGridCount: number;
    visibleRoleTableCount: number;
    visibleRoleRowCount: number;
    tableSummaries: Array<{
      index: number;
      nearbyTextSnippet: string;
      rowCount: number;
      firstRows: string[][];
      keywordMatches: string[];
    }>;
    gridSummaries: Array<{
      index: number;
      typeHint: string;
      nearbyTextSnippet: string;
      childTextChunks: string[];
      keywordMatches: string[];
    }>;
  };
  headerMatches?: Array<{
    text: string;
    tagName: string;
    role: string;
    className: string;
    ancestorTextSnippet: string;
    ancestorTagChain: string;
  }>;
}

function createFakeFrame({
  calls,
  label,
  url,
  title,
  diagnostics,
  overrides
}: {
  calls: string[];
  label: string;
  url: string;
  title: string;
  diagnostics: FrameDiagnosticsPayload;
  overrides?: Record<string, unknown>;
}) {
  return {
    url() {
      return url;
    },
    async title() {
      return title;
    },
    async evaluate(pageFunction: string | (() => unknown)) {
      calls.push(`frame-evaluate:${label}:${typeof pageFunction}`);
      if (typeof pageFunction === 'string') {
        return diagnostics;
      }

      return [fakeMarketWatchRow];
    },
    ...overrides
  };
}
