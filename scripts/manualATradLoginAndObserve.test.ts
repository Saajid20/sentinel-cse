import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { ATRAD_STORAGE_STATE_PATH, DEFAULT_ATRAD_BASE_URL } from './manualATradLogin.js';
import {
  createManualATradLoginAndObserveConfig,
  formatManualATradLoginAndObserveInstructions,
  runManualATradLoginAndObserve,
  type ManualATradLoginAndObserveRuntime
} from './manualATradLoginAndObserve.js';

const fakeMarketWatchRow = {
  Security: 'SAMP.N0000',
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
  Time: '10:35:00'
};

describe('manual ATrad login-and-observe script helpers', () => {
  it('uses the login URL by default and parses diagnose/debug flags', () => {
    const config = createManualATradLoginAndObserveConfig(['--diagnose', '--debug-rows']);

    expect(config).toEqual({
      baseUrl: new URL(DEFAULT_ATRAD_BASE_URL).toString(),
      storageStatePath: ATRAD_STORAGE_STATE_PATH,
      diagnose: true,
      debugRows: true,
      headless: false,
      readonlyMode: true
    });
  });

  it('prints manual same-session instructions', () => {
    const instructions = formatManualATradLoginAndObserveInstructions(
      createManualATradLoginAndObserveConfig()
    );

    expect(instructions).toContain(
      'Log in manually, complete 2FA if needed, navigate to Market Watch/home page, then return to this terminal and press Enter.'
    );
    expect(instructions.join('\n')).toContain(ATRAD_STORAGE_STATE_PATH);
  });

  it('waits for manual confirmation before observing', async () => {
    const calls: string[] = [];
    const runtime = createFakeRuntime({
      calls,
      activePageMode: 'observe'
    });

    const result = await runManualATradLoginAndObserve(
      createManualATradLoginAndObserveConfig(),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.rawRows).toEqual([fakeMarketWatchRow]);
    expect(calls.indexOf('wait')).toBeGreaterThan(calls.indexOf(`goto:${new URL(DEFAULT_ATRAD_BASE_URL).toString()}`));
    expect(calls.indexOf('wait')).toBeLessThan(calls.indexOf('evaluate:active:string'));
    expect(calls).toContain(`storage:${ATRAD_STORAGE_STATE_PATH}`);
  });

  it('uses the current active page for diagnostics after manual confirmation', async () => {
    const calls: string[] = [];
    const runtime = createFakeRuntime({
      calls,
      activePageMode: 'diagnose'
    });

    const result = await runManualATradLoginAndObserve(
      createManualATradLoginAndObserveConfig(['--diagnose']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.message).toContain('diagnostics');
    expect(result.rawRows).toEqual([]);
    expect(result.diagnostics?.pageUrl).toBe('https://atrad.example.com/watch');
    expect(calls).toContain('evaluate:active:string');
    expect(calls).not.toContain('evaluate:initial:string');
  });

  it('reuses observe helpers for same-session row debug after manual confirmation', async () => {
    const calls: string[] = [];
    const runtime = createFakeRuntime({
      calls,
      activePageMode: 'debug'
    });

    const result = await runManualATradLoginAndObserve(
      createManualATradLoginAndObserveConfig(['--debug-rows']),
      runtime
    );

    expect(result.ok).toBe(true);
    expect(result.message).toContain('row debug');
    expect(result.extractionDebug?.candidateCount).toBe(1);
    expect(calls).toContain('evaluate:active:string');
    expect(calls).not.toContain('evaluate:initial:string');
  });

  it('does not read credentials, environment variables, or include order action strings', () => {
    const source = readFileSync('scripts/manualATradLoginAndObserve.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password|otp/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|quantity|price input|market order|limit order/i);
    expect(source).not.toMatch(/click\(|fill\(|type\(/);
  });
});

function createFakeRuntime({
  calls,
  activePageMode
}: {
  calls: string[];
  activePageMode: 'observe' | 'diagnose' | 'debug';
}): ManualATradLoginAndObserveRuntime {
  let phase: 'before-wait' | 'after-wait' = 'before-wait';

  const initialPage = createFakePage({
    calls,
    label: 'initial',
    url: new URL(DEFAULT_ATRAD_BASE_URL).toString(),
    title: 'ATrad Login',
    mode: 'diagnose'
  });
  const activePage = createFakePage({
    calls,
    label: 'active',
    url: 'https://atrad.example.com/watch?session=secret',
    title: 'Market Watch 123456',
    mode: activePageMode
  });

  return {
    async launchSession() {
      calls.push('launch-session');
      return {
        session: {
          pages() {
            return phase === 'before-wait' ? [initialPage] : [initialPage, activePage];
          },
          async newPage() {
            calls.push('new-page');
            return initialPage;
          },
          async storageState(options: { path: string }) {
            calls.push(`storage:${options.path}`);
          }
        },
        async close() {
          calls.push('close');
        }
      };
    },
    async waitForUser() {
      calls.push('wait');
      phase = 'after-wait';
    },
    now: () => 1_000,
    log: (message) => calls.push(`log:${message}`)
  };
}

function createFakePage({
  calls,
  label,
  url,
  title,
  mode
}: {
  calls: string[];
  label: string;
  url: string;
  title: string;
  mode: 'observe' | 'diagnose' | 'debug';
}) {
  return {
    url() {
      return url;
    },
    async title() {
      return title;
    },
    frames() {
      return [this];
    },
    async goto(target: string, _options: { waitUntil: 'domcontentloaded'; timeout: number }) {
      calls.push(`goto:${target}`);
    },
    async evaluate(pageFunction: string | (() => unknown)) {
      calls.push(`evaluate:${label}:${typeof pageFunction}`);
      if (typeof pageFunction !== 'string') {
        return [];
      }

      if (pageFunction.includes("querySelectorAll('iframe').length")) {
        return 0;
      }

      if ((mode === 'observe' || mode === 'debug') && pageFunction.includes('const allowedHeaders =')) {
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

      return {
        tableCount: 1,
        rowCount: 2,
        visibleTextCount: 2,
        firstVisibleTextSnippets: ['Market Watch', 'Security [redacted-number]'],
        keywordMatches: ['Market Watch', 'Security [redacted-number]']
      };
    }
  };
}
