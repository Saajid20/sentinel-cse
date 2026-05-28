import { describe, expect, it } from 'vitest';
import { DEFAULT_OPENING_MOMENTUM_PARAMETERS } from '../packages/strategies/src/index.js';
import {
  BASELINE_OPENING_MOMENTUM_PARAMETERS,
  FIXED_OPENING_MOMENTUM_VARIANTS,
  buildATradReplayStrategyVariantsJsonExport,
  createManualATradReplayStrategyVariantsConfig,
  formatATradReplayStrategyVariantsSummary,
  runManualATradReplayStrategyVariants,
  type ManualATradReplayStrategyVariantsRuntime
} from './manualATradReplayStrategyVariants.js';

function buildSessionWithTriggerVolume(volume: number) {
  return {
    sessionId: 'atrad-session-variant-test',
    source: 'atrad-full-watch-equity',
    startedAt: '2026-05-26T05:47:22.000Z',
    endedAt: '2026-05-26T05:57:22.000Z',
    snapshots: [
      {
        ticker: 'SAMP.N0000',
        timestamp: 0,
        lastPrice: 50,
        bestBid: 49.8,
        bestAsk: 50,
        bidDepth: 200,
        askDepth: 100,
        volume: 100,
        totalTurnover: 5000
      },
      {
        ticker: 'SAMP.N0000',
        timestamp: 300_000,
        lastPrice: 55,
        bestBid: 54.9,
        bestAsk: 55,
        bidDepth: 200,
        askDepth: 100,
        volume,
        totalTurnover: volume * 55
      }
    ]
  };
}

function buildSessionWithTriggerVolumeAndImbalance(volume: number, bidDepth: number, askDepth: number) {
  return {
    sessionId: 'atrad-session-variant-test',
    source: 'atrad-full-watch-equity',
    startedAt: '2026-05-26T05:47:22.000Z',
    endedAt: '2026-05-26T05:57:22.000Z',
    snapshots: [
      {
        ticker: 'SAMP.N0000',
        timestamp: 0,
        lastPrice: 50,
        bestBid: 49.8,
        bestAsk: 50,
        bidDepth: 200,
        askDepth: 100,
        volume: 100,
        totalTurnover: 5000
      },
      {
        ticker: 'SAMP.N0000',
        timestamp: 300_000,
        lastPrice: 55,
        bestBid: 54.9,
        bestAsk: 55,
        bidDepth,
        askDepth,
        volume,
        totalTurnover: volume * 55
      }
    ]
  };
}

function createRuntime(
  session: Record<string, unknown>,
  calls: string[] = []
): ManualATradReplayStrategyVariantsRuntime {
  return {
    async readFile() {
      return JSON.stringify(session);
    },
    async ensureDir() {},
    async writeFile() {},
    log(message) {
      calls.push(message);
    }
  };
}

function variantByName(
  result: Awaited<ReturnType<typeof runManualATradReplayStrategyVariants>>,
  name: string
) {
  const variant = result.variants.find((item) => item.name === name);
  expect(variant).toBeDefined();
  return variant!;
}

describe('manual ATrad replay strategy variants', () => {
  it('parses the CLI config with input and top', () => {
    const config = createManualATradReplayStrategyVariantsConfig([
      '--input',
      'data/live-sessions/example.json',
      '--top',
      '20'
    ]);

    expect(config).toEqual({
      inputPath: 'data/live-sessions/example.json',
      topSignalTickers: 20,
      readonlyMode: true
    });
  });

  it('CLI parsing accepts --variant-json-output', () => {
    const config = createManualATradReplayStrategyVariantsConfig([
      '--input',
      'data/live-sessions/example.json',
      '--top',
      '20',
      '--variant-json-output',
      '.runtime-pipeline/variant-comparison.json'
    ]);

    expect(config).toEqual({
      inputPath: 'data/live-sessions/example.json',
      topSignalTickers: 20,
      variantJsonOutputPath: '.runtime-pipeline/variant-comparison.json',
      readonlyMode: true
    });
  });

  it('baseline variant uses default parameters and default strategy name', async () => {
    const session = buildSessionWithTriggerVolume(3000);
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    const baseline = variantByName(result, 'baseline');
    expect(baseline?.name).toBe('baseline');
    expect(baseline?.parameterOverrides).toEqual({});
    expect(baseline?.signalsGenerated).toBe(1);
    expect(baseline?.generatedStrategies).toEqual([
      DEFAULT_OPENING_MOMENTUM_PARAMETERS.strategyName
    ]);
  });

  it('detector overrides are passed without mutating defaults', async () => {
    const session = buildSessionWithTriggerVolume(500);
    const defaultBefore = { ...DEFAULT_OPENING_MOMENTUM_PARAMETERS };

    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    const baseline = variantByName(result, 'baseline');
    const volumeDisabled = variantByName(result, 'volume-ratio-disabled-diagnostic');
    const lowerVolume = variantByName(result, 'lower-volume-ratio-threshold');
    const imbalanceDisabled = variantByName(result, 'imbalance-disabled-diagnostic');
    const volumeAndImbalanceDisabled = variantByName(
      result,
      'volume-and-imbalance-disabled-diagnostic'
    );

    expect(baseline?.signalsGenerated).toBe(0);
    expect(volumeDisabled?.signalsGenerated).toBe(1);
    expect(lowerVolume?.signalsGenerated).toBe(0);
    expect(imbalanceDisabled?.signalsGenerated).toBe(0);
    expect(volumeAndImbalanceDisabled?.signalsGenerated).toBe(1);
    expect(DEFAULT_OPENING_MOMENTUM_PARAMETERS).toEqual(defaultBefore);
    expect(BASELINE_OPENING_MOMENTUM_PARAMETERS).toEqual(defaultBefore);
  });

  it('imbalance-disabled-diagnostic appears in deterministic variant order', () => {
    expect(FIXED_OPENING_MOMENTUM_VARIANTS.map((variant) => variant.name)).toEqual([
      'baseline',
      'volume-ratio-disabled-diagnostic',
      'lower-volume-ratio-threshold',
      'imbalance-disabled-diagnostic',
      'volume-and-imbalance-disabled-diagnostic'
    ]);
  });

  it('volume-ratio-disabled diagnostic variant changes results on a controlled fixture', async () => {
    const session = buildSessionWithTriggerVolume(500);
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    expect(result.variants[0]?.signalsGenerated).toBe(0);
    expect(variantByName(result, 'volume-ratio-disabled-diagnostic').signalsGenerated).toBe(1);
    expect(variantByName(result, 'volume-ratio-disabled-diagnostic').signalTickerCounts).toEqual([
      { ticker: 'SAMP.N0000', count: 1 }
    ]);
  });

  it('lower-volume-ratio variant changes results deterministically on a controlled fixture', async () => {
    const session = buildSessionWithTriggerVolume(1500);
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    expect(variantByName(result, 'baseline').signalsGenerated).toBe(0);
    expect(variantByName(result, 'volume-ratio-disabled-diagnostic').signalsGenerated).toBe(1);
    expect(variantByName(result, 'lower-volume-ratio-threshold').signalsGenerated).toBe(1);
    expect(variantByName(result, 'lower-volume-ratio-threshold').signalTickerCounts).toEqual([
      { ticker: 'SAMP.N0000', count: 1 }
    ]);
  });

  it('imbalance-disabled variant changes results on a controlled fixture where imbalance is the only blocker', async () => {
    const session = buildSessionWithTriggerVolumeAndImbalance(3000, 100, 200);
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    expect(variantByName(result, 'baseline').signalsGenerated).toBe(0);
    expect(variantByName(result, 'volume-ratio-disabled-diagnostic').signalsGenerated).toBe(0);
    expect(variantByName(result, 'imbalance-disabled-diagnostic').signalsGenerated).toBe(1);
  });

  it('volume-and-imbalance-disabled-diagnostic changes results deterministically when both gates block baseline', async () => {
    const session = buildSessionWithTriggerVolumeAndImbalance(500, 100, 200);
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      createRuntime(session)
    );

    expect(variantByName(result, 'baseline').signalsGenerated).toBe(0);
    expect(variantByName(result, 'volume-ratio-disabled-diagnostic').signalsGenerated).toBe(0);
    expect(variantByName(result, 'imbalance-disabled-diagnostic').signalsGenerated).toBe(0);
    expect(variantByName(result, 'volume-and-imbalance-disabled-diagnostic').signalsGenerated).toBe(1);
  });

  it('runner is SHADOW and readonly only', async () => {
    const session = buildSessionWithTriggerVolume(3000);
    const logs: string[] = [];
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json', '--top', '1']),
      createRuntime(session, logs)
    );

    expect(result.variants.every((variant) => variant.runtimeMode === 'SHADOW')).toBe(true);
    expect(logs.join('\n')).toContain('warning: offline research only; SHADOW replay only; no production thresholds changed');
    expect(() =>
      runManualATradReplayStrategyVariants(
        {
          inputPath: 'fixture.json',
          topSignalTickers: 1,
          readonlyMode: false as true
        },
        createRuntime(session)
      )
    ).rejects.toThrow('ATrad strategy variant replay must run in readonlyMode.');
  });

  it('formats a terminal summary with top signal ticker limits', async () => {
    const session = {
      sessionId: 'atrad-session-variant-test',
      source: 'atrad-full-watch-equity',
      startedAt: '2026-05-26T05:47:22.000Z',
      endedAt: '2026-05-26T05:57:22.000Z',
      snapshots: [
        {
          ticker: 'ALFA.N0000',
          timestamp: 0,
          lastPrice: 50,
          bestBid: 49.8,
          bestAsk: 50,
          bidDepth: 200,
          askDepth: 100,
          volume: 100,
          totalTurnover: 5000
        },
        {
          ticker: 'BETA.N0000',
          timestamp: 1,
          lastPrice: 50,
          bestBid: 49.8,
          bestAsk: 50,
          bidDepth: 200,
          askDepth: 100,
          volume: 100,
          totalTurnover: 5000
        },
        {
          ticker: 'ALFA.N0000',
          timestamp: 300_000,
          lastPrice: 55,
          bestBid: 54.9,
          bestAsk: 55,
          bidDepth: 200,
          askDepth: 100,
          volume: 3000,
          totalTurnover: 165000
        },
        {
          ticker: 'BETA.N0000',
          timestamp: 300_001,
          lastPrice: 55,
          bestBid: 54.9,
          bestAsk: 55,
          bidDepth: 200,
          askDepth: 100,
          volume: 3000,
          totalTurnover: 165000
        }
      ]
    };
    const result = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json', '--top', '1']),
      createRuntime(session)
    );

    const summary = formatATradReplayStrategyVariantsSummary(result).join('\n');

    expect(summary).toContain('top signal tickers per variant: 1');
    expect(summary).toContain('variant: baseline');
    expect(summary).toContain('variant: imbalance-disabled-diagnostic');
    expect(summary).toContain('variant: volume-and-imbalance-disabled-diagnostic');
    expect(summary).toContain('- parameter overrides: orderBookImbalanceThreshold=-1');
    expect(summary).toContain('- parameter overrides: orderBookImbalanceThreshold=-1, volumeRatioThreshold=-1');
    expect(summary).toContain('- top signal tickers: ALFA.N0000:1');
    expect(summary).not.toContain('BETA.N0000:1, ALFA.N0000:1');
  });

  it('JSON is written only when the flag is passed and leaves input untouched', async () => {
    const session = buildSessionWithTriggerVolume(3000);
    const writes: Array<{ path: string; contents: string }> = [];
    const reads: string[] = [];
    const runtime: ManualATradReplayStrategyVariantsRuntime = {
      async readFile(path) {
        reads.push(path);
        return JSON.stringify(session);
      },
      async ensureDir() {},
      async writeFile(path, contents) {
        writes.push({ path, contents });
      },
      log() {}
    };

    const withoutExport = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig(['--input', 'fixture.json']),
      runtime
    );
    const withExport = await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig([
        '--input',
        'fixture.json',
        '--variant-json-output',
        '.runtime-pipeline/variant-comparison.json'
      ]),
      runtime
    );

    expect(reads).toEqual(['fixture.json', 'fixture.json']);
    expect(withoutExport.variantJsonOutputPath).toBeUndefined();
    expect(withExport.variantJsonOutputPath).toBe('.runtime-pipeline/variant-comparison.json');
    expect(writes).toHaveLength(1);
    expect(writes[0]?.path).toBe('.runtime-pipeline/variant-comparison.json');
  });

  it('export includes top-level session fields and inputPath', async () => {
    const session = buildSessionWithTriggerVolume(3000);
    const writes: Array<{ path: string; contents: string }> = [];
    const runtime: ManualATradReplayStrategyVariantsRuntime = {
      async readFile() {
        return JSON.stringify(session);
      },
      async ensureDir() {},
      async writeFile(path, contents) {
        writes.push({ path, contents });
      },
      log() {}
    };

    await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig([
        '--input',
        'fixture.json',
        '--top',
        '3',
        '--variant-json-output',
        '.runtime-pipeline/variant-comparison.json'
      ]),
      runtime
    );

    const exported = JSON.parse(writes[0]?.contents ?? '{}');
    expect(exported).toMatchObject({
      sessionId: 'atrad-session-variant-test',
      inputPath: 'fixture.json',
      source: 'atrad-full-watch-equity',
      startedAt: '2026-05-26T05:47:22.000Z',
      endedAt: '2026-05-26T05:57:22.000Z',
      totalSnapshotsLoaded: 2,
      uniqueTickers: 1,
      topSignalTickerLimit: 3
    });
  });

  it('export includes full variants array with existing computed fields and preserves deterministic order', async () => {
    const session = buildSessionWithTriggerVolumeAndImbalance(500, 100, 200);
    const writes: Array<{ path: string; contents: string }> = [];
    const runtime: ManualATradReplayStrategyVariantsRuntime = {
      async readFile() {
        return JSON.stringify(session);
      },
      async ensureDir() {},
      async writeFile(path, contents) {
        writes.push({ path, contents });
      },
      log() {}
    };

    await runManualATradReplayStrategyVariants(
      createManualATradReplayStrategyVariantsConfig([
        '--input',
        'fixture.json',
        '--variant-json-output',
        '.runtime-pipeline/variant-comparison.json'
      ]),
      runtime
    );

    const exported = JSON.parse(writes[0]?.contents ?? '{}');
    expect(exported.variants.map((variant: { variantName: string }) => variant.variantName)).toEqual([
      'baseline',
      'volume-ratio-disabled-diagnostic',
      'lower-volume-ratio-threshold',
      'imbalance-disabled-diagnostic',
      'volume-and-imbalance-disabled-diagnostic'
    ]);
    expect(exported.variants[0]).toMatchObject({
      variantName: 'baseline',
      diagnosticOnly: false,
      runtimeMode: 'SHADOW',
      replayedSnapshots: 2,
      signalsGenerated: 0,
      uniqueSignalTickers: 0,
      generatedStrategies: [],
      signalTickerCounts: []
    });
    expect(exported.variants[4]).toMatchObject({
      variantName: 'volume-and-imbalance-disabled-diagnostic',
      diagnosticOnly: true,
      runtimeMode: 'SHADOW',
      replayedSnapshots: 2,
      signalsGenerated: 1,
      uniqueSignalTickers: 1,
      generatedStrategies: [DEFAULT_OPENING_MOMENTUM_PARAMETERS.strategyName],
      signalTickerCounts: [{ ticker: 'SAMP.N0000', count: 1 }]
    });
  });

  it('export works when a variant has zero signals and empty signalTickerCounts', () => {
    const exported = buildATradReplayStrategyVariantsJsonExport(
      createManualATradReplayStrategyVariantsConfig([
        '--input',
        'fixture.json',
        '--variant-json-output',
        '.runtime-pipeline/variant-comparison.json'
      ]),
      {
        ok: true,
        message: 'done',
        sessionId: 'atrad-session-variant-test',
        source: 'atrad-full-watch-equity',
        startedAt: '2026-05-26T05:47:22.000Z',
        endedAt: '2026-05-26T05:57:22.000Z',
        totalSnapshotsLoaded: 2,
        uniqueTickers: 1,
        topSignalTickerLimit: 10,
        variants: [
          {
            name: 'baseline',
            diagnosticOnly: false,
            description: 'Default Opening Momentum detector parameters.',
            parameterOverrides: {},
            runtimeMode: 'SHADOW',
            replayedSnapshots: 2,
            signalsGenerated: 0,
            uniqueSignalTickers: 0,
            signalTickerCounts: [],
            generatedStrategies: []
          }
        ],
        variantJsonOutputPath: '.runtime-pipeline/variant-comparison.json'
      }
    );

    expect(exported.variants).toEqual([
      {
        variantName: 'baseline',
        diagnosticOnly: false,
        description: 'Default Opening Momentum detector parameters.',
        parameterOverrides: {},
        runtimeMode: 'SHADOW',
        replayedSnapshots: 2,
        signalsGenerated: 0,
        uniqueSignalTickers: 0,
        generatedStrategies: [],
        signalTickerCounts: []
      }
    ]);
  });
});
