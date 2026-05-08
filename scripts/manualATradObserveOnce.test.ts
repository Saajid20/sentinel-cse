import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';
import { MarketDataSanitizer } from '../packages/core/src/index.js';
import { ATRAD_PERSISTENT_PROFILE_PATH, ATRAD_STORAGE_STATE_PATH } from './manualATradLogin.js';
import {
  assessATradParsedSnapshotQuality,
  analyzeMarketWatchRows,
  buildATradParsedRowQualitySummary,
  buildMarketWatchRowFromCells,
  collectPageDiagnostics,
  createManualATradObserveOnceConfig,
  DEFAULT_ATRAD_MARKET_WATCH_URL,
  extractVisibleMarketWatchRows,
  formatObserveOnceSummary,
  ManualATradObserveOnceRuntime,
  marketWatchRowToRawSnapshot,
  normalizeATradFullWatchEquityRow,
  parseDojoWatchGridRow,
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

  it('parses the raw output flag from CLI args', () => {
    const config = createManualATradObserveOnceConfig(['--raw-output']);

    expect(config.rawOutput).toBe(true);
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

  it('parses a Dojo ticker-like row conservatively', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      ['ASCO.N0000']
    );

    expect(row).toEqual({
      Security: 'ASCO.N0000'
    });
  });

  it('cleans malformed CIC ticker suffix noise', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      ['CIC.N0000C`', 'C I C Holdings PLC', '1,000', '78.50', '79.00', '600', '78.80', '12,500']
    );

    expect(row.Security).toBe('CIC.N0000');
  });

  it('cleans malformed LOLC ticker suffix noise', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      ['LOLC.N0000C`', 'LOLC Holdings PLC', '1,000', '510.00', '512.00', '200', '511.00', '4,200']
    );

    expect(row.Security).toBe('LOLC.N0000');
  });

  it('cleans malformed COMB ticker suffix noise', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      ['COMB.N0000C`', 'Commercial Bank PLC', '1,000', '141.00', '141.25', '500', '141.10', '8,500']
    );

    expect(row.Security).toBe('COMB.N0000');
  });

  it('parses a rich Dojo row with ticker, bid/ask, last, and volume', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      ['ASCO.N0000', 'Associated Motorways PLC', '1,000', '54.50', '55.00', '800', '55.00', '12,500']
    );
    const rawSnapshot = marketWatchRowToRawSnapshot(row, 1_000);

    expect(row).toMatchObject({
      Security: 'ASCO.N0000',
      'Company Name': 'Associated Motorways PLC',
      'Bid Qty': '1,000',
      'Bid Price': '54.50',
      'Ask Price': '55.00',
      Last: '55.00',
      Volume: '12,500'
    });
    expect(rawSnapshot).toMatchObject({
      ticker: 'ASCO.N0000',
      bidDepth: '1000',
      bestBid: '54.50',
      bestAsk: '55.00',
      lastPrice: '55.00',
      volume: '12500'
    });
  });

  it('maps a merged multi-view Dojo row into a RawMarketSnapshot', () => {
    const row = parseDojoWatchGridRow(
      [
        'Security',
        'Company Name',
        'Bid Qty',
        'Bid Price',
        'Ask Price',
        'Ask Qty',
        'Last',
        'Last Qty',
        'Volume',
        'Turnover'
      ],
      [
        'CDB.N0000',
        'Ceylon Development Bank PLC',
        '2,500',
        '54.50',
        '55.00',
        '1,800',
        '55.00',
        '500',
        '12,500',
        '687,500'
      ]
    );
    const rawSnapshot = marketWatchRowToRawSnapshot(row, 1_000);

    expect(row).toMatchObject({
      Security: 'CDB.N0000',
      'Company Name': 'Ceylon Development Bank PLC',
      'Bid Qty': '2,500',
      'Bid Price': '54.50',
      'Ask Price': '55.00',
      'Ask Qty': '1,800',
      Last: '55.00',
      'Last Qty': '500',
      Volume: '12,500',
      Turnover: '687,500'
    });
    expect(rawSnapshot).toMatchObject({
      ticker: 'CDB.N0000',
      bidDepth: '2500',
      bestBid: '54.50',
      bestAsk: '55.00',
      askDepth: '1800',
      lastPrice: '55.00',
      volume: '12500',
      totalTurnover: '687500'
    });
  });

  it('normalizes a real-shaped MGT Full Watch Equity row with trailing Time', () => {
    const row = normalizeATradFullWatchEquityRow([
      'MGT.N0000',
      'HAYLEYS FABRIC PLC',
      '11,100',
      '31.70',
      '31.90',
      '6,343',
      '31.80',
      '97',
      '0.40',
      '1.27',
      '32.00',
      '31.86',
      '4,821',
      '153,588.60',
      '22',
      '31.40',
      '34.15%',
      '10:15:47.383159'
    ]);
    const rawSnapshot = marketWatchRowToRawSnapshot(row, 1_000);

    expect(row).toMatchObject({
      Security: 'MGT.N0000',
      'Company Name': 'HAYLEYS FABRIC PLC',
      'Bid Qty': '11,100',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      'Ask Qty': '6,343',
      Last: '31.80',
      'Last Qty': '97',
      Change: '0.40',
      '% Change': '1.27',
      High: '32.00',
      VWA: '31.86',
      Volume: '4,821',
      Turnover: '153,588.60',
      Trades: '22',
      'Price Close': '31.40',
      'Buy Sentiment': '34.15%',
      Time: '10:15:47.383159'
    });
    expect(row.Low).toBeUndefined();
    expect(rawSnapshot).toMatchObject({
      ticker: 'MGT.N0000',
      lastPrice: '31.80',
      bestBid: '31.70',
      bestAsk: '31.90',
      bidDepth: '11100',
      askDepth: '6343',
      volume: '4821',
      totalTurnover: '153588.60'
    });
    expect(rawSnapshot.metadata).toMatchObject({
      companyName: 'HAYLEYS FABRIC PLC',
      lastQty: '97',
      change: '0.40',
      percentChange: '1.27',
      high: '32.00',
      low: undefined,
      vwa: '31.86',
      trades: '22',
      priceClose: '31.40',
      buySentiment: '34.15%',
      time: '10:15:47.383159'
    });
  });

  it('normalizes a shifted ASIY row conservatively with Last=100', () => {
    const row = normalizeATradFullWatchEquityRow([
      'ASIY.N0000',
      'ASIA SIYAKA COMMODITIES PLC',
      '5,000',
      '99.00',
      '100.00',
      '2,000',
      '100',
      '150',
      '1.00',
      '1.01',
      '101.00',
      '12,500',
      '1,250,000.00',
      '9',
      '99.00',
      '15.50%',
      '10:15:48.000000'
    ]);

    expect(row).toMatchObject({
      Security: 'ASIY.N0000',
      Last: '100',
      Volume: '12,500',
      Turnover: '1,250,000.00',
      Trades: '9',
      'Price Close': '99.00',
      'Buy Sentiment': '15.50%',
      Time: '10:15:48.000000'
    });
  });

  it('recovers DFCC last from a later price-like field instead of trusting an early quantity-like value', () => {
    const row = normalizeATradFullWatchEquityRow([
      'DFCC.N0000',
      'DFCC BANK PLC',
      '1,000',
      '141.00',
      '141.25',
      '2,500',
      '70',
      '141.10',
      '3,500',
      '0.10',
      '0.07',
      '141.50',
      '141.05',
      '250,000',
      '35,275,000.00',
      '48',
      '140.80',
      '44.00%',
      '10:15:50'
    ]);

    expect(row).toMatchObject({
      Security: 'DFCC.N0000',
      Last: '141.10',
      'Last Qty': '3,500',
      Volume: '250,000',
      Turnover: '35,275,000.00',
      Trades: '48',
      'Price Close': '140.80',
      'Buy Sentiment': '44.00%',
      Time: '10:15:50'
    });
    expect(row.Change).toBe('0.10');
  });

  it('recovers KOTA last from a later price-like field instead of a quantity-like 3,500 cell', () => {
    const row = normalizeATradFullWatchEquityRow([
      'KOTA.N0000',
      'KOTAGALA PLANTATIONS PLC',
      '5,000',
      '10.20',
      '10.30',
      '4,500',
      '3,500',
      '10.25',
      '1,250',
      '0.05',
      '0.49',
      '10.40',
      '10.15',
      '85,000',
      '872,000.00',
      '18',
      '10.10',
      '20.00%',
      '10:15:51'
    ]);
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(row).toMatchObject({
      Security: 'KOTA.N0000',
      Last: '10.25',
      'Last Qty': '1,250',
      Volume: '85,000',
      Turnover: '872,000.00'
    });
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('LAST_LOOKS_LIKE_QUANTITY');
  });

  it('does not map a shorter HNB row percent field as Volume', () => {
    const row = normalizeATradFullWatchEquityRow([
      'HNB.N0000',
      'HATTON NATIONAL BANK PLC',
      '5,000',
      '290.00',
      '291.00',
      '1,000',
      '290.50',
      '200',
      '1.72%',
      '292.00',
      '289.50',
      '290.00',
      '12.00%',
      '10:15:49'
    ]);

    expect(row).toMatchObject({
      Security: 'HNB.N0000',
      Last: '290.50',
      'Buy Sentiment': '12.00%',
      Time: '10:15:49'
    });
    expect(row.Volume).toBeUndefined();
    expect(row.Turnover).toBeUndefined();
  });

  it('maps an HNB-like full trailing section with Trades, Buy Sentiment, and Time correctly', () => {
    const row = normalizeATradFullWatchEquityRow([
      'HNB.N0000',
      'HATTON NATIONAL BANK PLC',
      '15,000',
      '414.00',
      '414.25',
      '10,000',
      '414.00',
      '16',
      '0.50',
      '0.12',
      '414.00',
      '413.50',
      '413.61',
      '137,542',
      '56,884,038.25',
      '205',
      '413.50',
      '34.23%',
      '12:26:15'
    ]);
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(row).toMatchObject({
      Security: 'HNB.N0000',
      Last: '414.00',
      'Last Qty': '16',
      High: '414.00',
      Low: '413.50',
      VWA: '413.61',
      Volume: '137,542',
      Turnover: '56,884,038.25',
      Trades: '205',
      'Price Close': '413.50',
      'Buy Sentiment': '34.23%',
      Time: '12:26:15'
    });
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('TRADES_LOOKS_LIKE_PERCENT');
  });

  it('moves a trailing percent into Buy Sentiment instead of Trades for PLC-like rows', () => {
    const row = {
      Security: 'PLC.N0000',
      'Bid Qty': '2,500',
      'Bid Price': '100.00',
      'Ask Price': '100.50',
      'Ask Qty': '1,200',
      Last: '100.25',
      Volume: '25,000',
      Turnover: '2,506,250.00',
      Trades: '18.20%',
      Time: '12:26:22'
    };
    const assessment = assessATradParsedSnapshotQuality(
      parseDojoWatchGridRow(
        ['Security', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume', 'Turnover', 'Trades', 'Time'],
        Object.values(row)
      ),
      marketWatchRowToRawSnapshot(
        parseDojoWatchGridRow(
          ['Security', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume', 'Turnover', 'Trades', 'Time'],
          Object.values(row)
        ),
        1_000
      ),
      { accepted: true, issues: [] }
    );

    expect(assessment.row['Buy Sentiment']).toBe('18.20%');
    expect(assessment.row.Trades).toBeUndefined();
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('TRADES_LOOKS_LIKE_PERCENT');
  });

  it('maps REEF volume and turnover from a longer real-shaped row', () => {
    const row = normalizeATradFullWatchEquityRow([
      'REEF.N0000',
      'CITRUS LEISURE PLC',
      '50,000',
      '4.70',
      '4.80',
      '12,500',
      '4.80',
      '2,500',
      '0.10',
      '2.13',
      '4.90',
      '4.75',
      '3,998,716',
      '19,145,319.50',
      '615',
      '4.70',
      '51.00%',
      '10:16:00'
    ]);

    expect(row).toMatchObject({
      Security: 'REEF.N0000',
      Volume: '3,998,716',
      Turnover: '19,145,319.50',
      Trades: '615',
      'Price Close': '4.70',
      'Buy Sentiment': '51.00%',
      Time: '10:16:00'
    });
  });

  it('leaves turnover-sized VWA candidates unset instead of mapping them as VWA', () => {
    const row = normalizeATradFullWatchEquityRow([
      'VWA2.N0000',
      'TURNOVER TEST PLC',
      '5,000',
      '31.70',
      '31.90',
      '6,343',
      '31.80',
      '97',
      '0.40',
      '1.27',
      '32.00',
      '153,588.60',
      '4,821',
      '153,588.60',
      '22',
      '31.40',
      '34.15%',
      '10:15:47.383159'
    ]);

    expect(row.VWA).toBeUndefined();
  });

  it('leaves JXG-like bad VWA candidates unset instead of flagging VWA outside price range', () => {
    const row = normalizeATradFullWatchEquityRow([
      'JXG.N0000',
      'JXG PLC',
      '5,000',
      '8.90',
      '9.00',
      '3,000',
      '8.95',
      '120',
      '0.05',
      '0.56',
      '9.10',
      '8.85',
      '240,000.00',
      '345,000',
      '3,087,750.00',
      '42',
      '8.90',
      '22.00%',
      '12:26:30'
    ]);
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(row.VWA).toBeUndefined();
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('VWA_OUTSIDE_PRICE_RANGE');
  });

  it('leaves SHOT-like bad VWA candidates unset instead of flagging VWA outside price range', () => {
    const row = normalizeATradFullWatchEquityRow([
      'SHOT.X0000',
      'SHOT PLC',
      '3,000',
      '12.40',
      '12.50',
      '1,500',
      '12.45',
      '60',
      '0.10',
      '0.81',
      '12.55',
      '12.35',
      '1,500,000.00',
      '85,000',
      '1,058,250.00',
      '15',
      '12.35',
      '30.00%',
      '12:26:35'
    ]);

    expect(row.VWA).toBeUndefined();
  });

  it('leaves KZOO-like bad VWA candidates unset instead of flagging VWA outside price range', () => {
    const row = normalizeATradFullWatchEquityRow([
      'KZOO.N0000',
      'KAZOO PLC',
      '2,000',
      '15.10',
      '15.20',
      '2,500',
      '15.15',
      '45',
      '0.05',
      '0.33',
      '15.30',
      '15.05',
      '8,750,000.00',
      '125,000',
      '1,893,750.00',
      '27',
      '15.05',
      '16.00%',
      '12:26:40'
    ]);

    expect(row.VWA).toBeUndefined();
  });

  it('keeps genuinely ambiguous last values at low confidence when no better price is recoverable', () => {
    const row = normalizeATradFullWatchEquityRow([
      'BADL.N0000',
      'AMBIGUOUS HOLDINGS PLC',
      '5,000',
      '10.20',
      '10.30',
      '4,500',
      '3,500',
      '1,250',
      '0.05',
      '0.49',
      '85,000',
      '872,000.00',
      '18',
      '10.10',
      '20.00%',
      '10:15:51'
    ]);
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(row.Last).toBeUndefined();
    expect(assessment.status).toBe('LOW_CONFIDENCE');
  });

  it('assigns high or medium confidence to a clean REEF-shaped row', () => {
    const row = normalizeATradFullWatchEquityRow([
      'REEF.N0000',
      'CITRUS LEISURE PLC',
      '50,000',
      '4.70',
      '4.80',
      '12,500',
      '4.80',
      '2,500',
      '0.10',
      '2.13',
      '4.90',
      '4.75',
      '3,998,716',
      '19,145,319.50',
      '615',
      '4.70',
      '51.00%',
      '10:16:00'
    ]);
    const rawSnapshot = marketWatchRowToRawSnapshot(row, 1_000);
    const assessment = assessATradParsedSnapshotQuality(row, rawSnapshot, { accepted: true, issues: [] });

    expect(['HIGH_CONFIDENCE', 'MEDIUM_CONFIDENCE']).toContain(assessment.status);
  });

  it('does not downgrade a clean row to low confidence just because VWA is missing', () => {
    const row = {
      Security: 'CIC.X0000',
      'Bid Qty': '2,500',
      'Bid Price': '72.00',
      'Ask Price': '72.20',
      'Ask Qty': '1,800',
      Last: '72.10',
      Volume: '12,500'
    };
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(['HIGH_CONFIDENCE', 'MEDIUM_CONFIDENCE']).toContain(assessment.status);
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('LOW_MAPPING_CONFIDENCE');
    expect(assessment.issues.map((issue) => issue.code)).not.toContain('VWA_OUTSIDE_PRICE_RANGE');
  });

  it('does not accept percent or time as Price Close', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Price Close', 'Buy Sentiment', 'Time', 'Volume'],
      ['BADP.N0000', '1,000', '50.00', '50.20', '900', '50.10', '12:26:22', '18.20%', '12:26:23', '5,000']
    );

    expect(row['Price Close']).toBeUndefined();
    expect(row.Time).toBe('12:26:23');
    expect(row['Buy Sentiment']).toBe('18.20%');
  });

  it('does not accept percent as Trades', () => {
    const row = parseDojoWatchGridRow(
      ['Security', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Trades', 'Buy Sentiment', 'Volume'],
      ['TRD.N0000', '1,000', '50.00', '50.20', '900', '50.10', '18.20%', '18.20%', '5,000']
    );

    expect(row.Trades).toBeUndefined();
    expect(row['Buy Sentiment']).toBe('18.20%');
  });

  it('retains price-like VWA values near bid ask and last', () => {
    const row = normalizeATradFullWatchEquityRow([
      'CIC.X0000',
      'CIC HOLDINGS PLC',
      '2,500',
      '72.00',
      '72.20',
      '1,800',
      '72.10',
      '400',
      '0.10',
      '0.14',
      '72.40',
      '72.00',
      '72.08',
      '12,500',
      '901,000.00',
      '14',
      '72.00',
      '18.00%',
      '10:15:52'
    ]);

    expect(row.VWA).toBe('72.08');
  });

  it('assigns high or medium confidence to a clean CDB-shaped row', () => {
    const row = parseDojoWatchGridRow(
      [
        'Security',
        'Company Name',
        'Bid Qty',
        'Bid Price',
        'Ask Price',
        'Ask Qty',
        'Last',
        'Last Qty',
        'Volume',
        'Turnover'
      ],
      [
        'CDB.N0000',
        'Ceylon Development Bank PLC',
        '2,500',
        '54.50',
        '55.00',
        '1,800',
        '55.00',
        '500',
        '12,500',
        '687,500'
      ]
    );
    const assessment = assessATradParsedSnapshotQuality(
      row,
      marketWatchRowToRawSnapshot(row, 1_000),
      { accepted: true, issues: [] }
    );

    expect(['HIGH_CONFIDENCE', 'MEDIUM_CONFIDENCE']).toContain(assessment.status);
  });

  it('flags last values that look like quantities', () => {
    const row = {
      Security: 'QTY.N0000',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      Last: '6343',
      Volume: '4,821'
    };
    const assessment = assessATradParsedSnapshotQuality(row, marketWatchRowToRawSnapshot(row, 1_000), {
      accepted: true,
      issues: []
    });

    expect(assessment.status).toBe('LOW_CONFIDENCE');
    expect(assessment.issues.map((issue) => issue.code)).toContain('LAST_LOOKS_LIKE_QUANTITY');
  });

  it('flags volume values that look like percents', () => {
    const row = {
      Security: 'PCT.N0000',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      Last: '31.80',
      Volume: '1.72%'
    };
    const assessment = assessATradParsedSnapshotQuality(row, marketWatchRowToRawSnapshot(row, 1_000), {
      accepted: true,
      issues: []
    });

    expect(assessment.issues.map((issue) => issue.code)).toContain('VOLUME_LOOKS_LIKE_PERCENT');
  });

  it('flags turnover values that look like times', () => {
    const row = {
      Security: 'TIME.N0000',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      Last: '31.80',
      Volume: '4,821',
      Turnover: '10:15:47.383159'
    };
    const assessment = assessATradParsedSnapshotQuality(row, marketWatchRowToRawSnapshot(row, 1_000), {
      accepted: true,
      issues: []
    });

    expect(assessment.issues.map((issue) => issue.code)).toContain('TURNOVER_LOOKS_LIKE_TIME');
  });

  it('flags VWA values that look turnover-sized', () => {
    const row = {
      Security: 'VWA.N0000',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      Last: '31.80',
      Volume: '4,821',
      VWA: '153,588.60'
    };
    const assessment = assessATradParsedSnapshotQuality(row, marketWatchRowToRawSnapshot(row, 1_000), {
      accepted: true,
      issues: []
    });

    expect(assessment.issues.map((issue) => issue.code)).toContain('VWA_OUTSIDE_PRICE_RANGE');
  });

  it('preserves ASPH-like sanitizer rejection while marking the row rejected', () => {
    const row = {
      Security: 'ASPH.N0000',
      'Bid Qty': '1,000',
      'Bid Price': '100.00',
      'Ask Price': '120.00',
      'Ask Qty': '800',
      Last: '110.00',
      Volume: '12,500'
    };
    const sanitizer = new MarketDataSanitizer({ source: 'atrad-market-watch' });
    const sanitized = sanitizer.sanitize(marketWatchRowToRawSnapshot(row, 1_000));
    const assessment = assessATradParsedSnapshotQuality(row, marketWatchRowToRawSnapshot(row, 1_000), sanitized);

    expect(sanitized.accepted).toBe(false);
    expect(sanitized.issues.map((issue) => issue.code)).toContain('UNREALISTIC_SPREAD');
    expect(assessment.status).toBe('REJECTED');
    expect(assessment.sanitizerIssueCodes).toContain('UNREALISTIC_SPREAD');
  });

  it('builds a concise quality summary in normal output', () => {
    const cleanRow = normalizeATradFullWatchEquityRow([
      'MGT.N0000',
      'HAYLEYS FABRIC PLC',
      '11,100',
      '31.70',
      '31.90',
      '6,343',
      '31.80',
      '97',
      '0.40',
      '1.27',
      '32.00',
      '31.86',
      '4,821',
      '153,588.60',
      '22',
      '31.40',
      '34.15%',
      '10:15:47.383159'
    ]);
    const lowConfidenceRow = {
      Security: 'LOW.N0000',
      'Bid Price': '31.70',
      'Ask Price': '31.90',
      Last: '6343',
      Volume: '4,821'
    };
    const cleanAssessment = assessATradParsedSnapshotQuality(
      cleanRow,
      marketWatchRowToRawSnapshot(cleanRow, 1_000),
      { accepted: true, issues: [] }
    );
    const lowAssessment = assessATradParsedSnapshotQuality(
      lowConfidenceRow,
      marketWatchRowToRawSnapshot(lowConfidenceRow, 1_000),
      { accepted: true, issues: [] }
    );
    const lines = formatObserveOnceSummary({
      ok: true,
      message: 'summary',
      rawRows: [cleanRow, lowConfidenceRow],
      rawSnapshots: [
        marketWatchRowToRawSnapshot(cleanRow, 1_000),
        marketWatchRowToRawSnapshot(lowConfidenceRow, 1_000)
      ],
      accepted: [
        {
          row: cleanRow,
          rawSnapshot: marketWatchRowToRawSnapshot(cleanRow, 1_000),
          snapshot: {
            ticker: 'MGT.N0000',
            timestamp: 1_000,
            lastPrice: 31.8,
            bestBid: 31.7,
            bestAsk: 31.9,
            bidDepth: 11100,
            askDepth: 6343,
            volume: 4821,
            totalTurnover: 153588.6
          },
          issues: []
        }
      ],
      rejected: [],
      qualityAssessments: [cleanAssessment, lowAssessment],
      qualitySummary: buildATradParsedRowQualitySummary([cleanAssessment, lowAssessment])
    });

    expect(lines.join('\n')).toContain('Quality summary:');
    expect(lines.join('\n')).toContain('low confidence: 1');
    expect(lines.join('\n')).not.toContain('"Security":');
  });

  it('rejects rows with insufficient required price fields', () => {
    const analyses = analyzeMarketWatchRows(
      'dojo-grid',
      ['Security', 'Company Name', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Last', 'Volume'],
      [['FAIL.N0000', 'Failed Equity PLC', '1,000', '12,500']],
      1_000
    );

    expect(analyses[0]?.accepted).toBe(false);
    expect(analyses[0]?.reasons).toEqual(
      expect.arrayContaining(['missing last price', 'missing bid/ask'])
    );
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
              kind: 'table',
              score: 80,
              headerRowIndex: 0,
              headerCells: Object.keys(fakeMarketWatchRow),
              containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
              rows: [Object.values(fakeMarketWatchRow)]
            }
          ],
          dojoCandidates: []
        };
      }
    });

    expect(rows).toEqual([fakeMarketWatchRow]);
    expect(typeof evaluateInput).toBe('string');
    expect(String(evaluateInput)).not.toContain('__name');
  });

  it('dedupes duplicate Dojo ticker rows and keeps the richer merged row', async () => {
    const rows = await extractVisibleMarketWatchRows({
      async goto() {
        throw new Error('goto should not be called by extractor');
      },
      async evaluate() {
        return {
          chosenCandidateIndex: 0,
          candidates: [
            {
              kind: 'dojo-grid',
              score: 110,
              headerRowIndex: 0,
              headerCells: [
                'Security',
                'Company Name',
                'Bid Qty',
                'Bid Price',
                'Ask Price',
                'Ask Qty',
                'Last',
                'Volume'
              ],
              containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
              rows: [
                ['CDB.N0000'],
                [
                  'CDB.N0000',
                  'Ceylon Development Bank PLC',
                  '2,500',
                  '54.50',
                  '55.00',
                  '1,800',
                  '55.00',
                  '12,500'
                ]
              ]
            }
          ],
          dojoCandidates: [
            {
              kind: 'dojo-grid',
              score: 110,
              headerRowIndex: 0,
              headerCells: [
                'Security',
                'Company Name',
                'Bid Qty',
                'Bid Price',
                'Ask Price',
                'Ask Qty',
                'Last',
                'Volume'
              ],
              containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
              rows: [
                ['CDB.N0000'],
                [
                  'CDB.N0000',
                  'Ceylon Development Bank PLC',
                  '2,500',
                  '54.50',
                  '55.00',
                  '1,800',
                  '55.00',
                  '12,500'
                ]
              ],
              viewCount: 2,
              viewSummaries: [
                {
                  viewIndex: 0,
                  rowCount: 2,
                  firstRows: [['CDB.N0000'], ['ATL.R0000']]
                },
                {
                  viewIndex: 1,
                  rowCount: 2,
                  firstRows: [
                    ['Ceylon Development Bank PLC', '2,500', '54.50', '55.00', '1,800', '55.00', '12,500'],
                    ['ACL Cables PLC', '900', '72.00', '72.50', '100', '72.25', '4,200']
                  ]
                }
              ]
            }
          ]
        };
      }
    });

    expect(rows).toEqual([
      {
        Security: 'CDB.N0000',
        'Company Name': 'Ceylon Development Bank PLC',
        'Bid Qty': '2,500',
        'Bid Price': '54.50',
        'Ask Price': '55.00',
        'Ask Qty': '1,800',
        Last: '55.00',
        Volume: '12,500'
      }
    ]);
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
            kind: 'table',
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

  it('reports detected Dojo watchgrids and ticker-only row rejections in debug output', async () => {
    const runtime = fakeRuntime({
      storageStateExists: true,
      calls: [],
      extractionCandidates: {
        chosenCandidateIndex: 0,
        candidates: [
          {
            kind: 'dojo-grid',
            score: 95,
            headerRowIndex: 0,
            headerCells: [
              'Security',
              'Company Name',
              'Bid Qty',
              'Bid Price',
              'Ask Price',
              'Ask Qty',
              'Last',
              'Volume'
            ],
            containerTextMatches: ['Security', 'Bid Price', 'Ask Price', 'Last', 'Volume'],
            rows: [
              ['ASCO.N0000'],
              [
                'MGT.N0000',
                'HAYLEYS FABRIC PLC',
                '11,100',
                '31.70',
                '31.90',
                '6,343',
                '31.80',
                '97',
                '0.40',
                '1.27',
                '32.00',
                '31.86',
                '4,821',
                '153,588.60',
                '22',
                '31.40',
                '34.15%',
                '10:15:47.383159'
              ]
            ]
          }
        ],
        dojoCandidates: [
          {
            kind: 'dojo-grid',
            score: 95,
            headerRowIndex: 0,
            headerCells: [
              'Security',
              'Company Name',
              'Bid Qty',
              'Bid Price',
              'Ask Price',
              'Ask Qty',
              'Last',
              'Volume'
            ],
            containerTextMatches: ['Security', 'Bid Price', 'Ask Price', 'Last', 'Volume'],
            rows: [
              ['ASCO.N0000'],
              [
                'MGT.N0000',
                'HAYLEYS FABRIC PLC',
                '11,100',
                '31.70',
                '31.90',
                '6,343',
                '31.80',
                '97',
                '0.40',
                '1.27',
                '32.00',
                '31.86',
                '4,821',
                '153,588.60',
                '22',
                '31.40',
                '34.15%',
                '10:15:47.383159'
              ]
            ],
            viewCount: 2,
            viewSummaries: [
              {
                viewIndex: 0,
                rowCount: 2,
                firstRows: [['ASCO.N0000'], ['MGT.N0000']]
              },
              {
                viewIndex: 1,
                rowCount: 2,
                firstRows: [
                  ['Associated Motorways PLC'],
                  ['HAYLEYS FABRIC PLC', '11,100', '31.70', '31.90', '6,343', '31.80', '97', '0.40']
                ]
              }
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

    expect(result.extractionDebug?.dojoDebug?.gridCount).toBe(1);
    expect(result.extractionDebug?.dojoDebug?.viewCount).toBe(2);
    expect(result.extractionDebug?.dojoDebug?.parsedRows[0]).toEqual({ Security: 'ASCO.N0000' });
    expect(result.extractionDebug?.dojoDebug?.rowAnalyses[0]?.reasons).toContain('ticker only');
    expect(lines).toContain('Detected Dojo watchgrid count: 1');
    expect(lines).toContain('Dojo grid view count: 2');
    expect(lines).toContain('Dojo view 0: rows=2');
    expect(lines).toContain('Dojo row 2: ["MGT.N0000","HAYLEYS FABRIC PLC","11,100","31.70","31.90","6,343","31.80","97","0.40","1.27","32.00","31.86","4,821","153,588.60","22","31.40","34.15%","10:15:47.383159"]');
    expect(lines).toContain('Dojo parsed row 1: {"Security":"ASCO.N0000"}');
    expect(lines).toContain('"Time":"10:15:47.383159"');
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
                    kind: 'table',
                    score: 80,
                    headerRowIndex: 0,
                    headerCells: Object.keys(fakeMarketWatchRow),
                    containerTextMatches: ['Market Watch', 'Full Watch', 'Equity'],
                    rows: [Object.values(fakeMarketWatchRow)]
                  }
                ],
                dojoCandidates: []
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
    kind: 'table' | 'dojo-grid';
    score: number;
    headerRowIndex: number;
    headerCells: string[];
    containerTextMatches: string[];
    rows: string[][];
  }>;
  dojoCandidates?: Array<{
    kind: 'dojo-grid';
    score: number;
    headerRowIndex: number;
    headerCells: string[];
    containerTextMatches: string[];
    rows: string[][];
    viewCount?: number;
    viewSummaries?: Array<{
      viewIndex: number;
      rowCount: number;
      firstRows: string[][];
    }>;
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
