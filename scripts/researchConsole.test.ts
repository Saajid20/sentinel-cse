import { describe, expect, it } from 'vitest';
import {
  createResearchConsoleConfig,
  runResearchConsole,
  type ResearchConsoleConfig,
  type ResearchConsoleRuntime
} from './researchConsole.js';

const config: ResearchConsoleConfig = {
  r11AnalysisDir: 'analysis',
  r11GoldLabelDir: 'gold',
  r10RetrievalDir: 'retrieval',
  json: false
};

function analysis(options: {
  ticker: string;
  metrics: Array<{ name: string; value: number; current: number; previous: number }>;
  scorecard: Record<string, unknown>;
  missing?: string[];
  reasons?: string[];
  generatedAt?: string;
}): string {
  return JSON.stringify({
    pdf_path: `C:\\pdfs\\cse_report_${options.ticker}_1.pdf`,
    generated_at: options.generatedAt ?? '2026-08-15T00:00:00.000Z',
    aggregated_metric_results: options.metrics.map((metric) => ({
      metric_name: metric.name,
      occurrence_count: 1,
      conflict: false,
      selected_metric: {
        metric_name: metric.name,
        value: metric.value,
        source_traces: [
          {
            page_number: 5,
            table_id: 'pypdf_page_5',
            row_label: 'Total Equity',
            raw_value: 'Total Equity 1 2'
          }
        ]
      },
      selected_audit_entry: {
        metric_name: metric.name,
        inputs: { current: metric.current, previous: metric.previous }
      }
    })),
    scorecard_build_result: {
      scorecard: options.scorecard,
      metric_names_used: options.metrics.map((metric) => metric.name),
      missing_expected_metrics: options.missing ?? [],
      manual_review_reasons: options.reasons ?? []
    }
  });
}

function runtimeFor(files: Record<string, Record<string, string>>): ResearchConsoleRuntime {
  return {
    readdir: async (path) => {
      const dir = files[path];
      if (!dir) throw new Error(`ENOENT ${path}`);
      return Object.keys(dir);
    },
    readFile: async (path) => {
      for (const [dir, entries] of Object.entries(files)) {
        for (const [name, body] of Object.entries(entries)) {
          if (path === `${dir}/${name}` || path === `${dir}\\${name}`) return body;
        }
      }
      throw new Error(`ENOENT ${path}`);
    },
    stat: async () => ({ isDirectory: () => false, mtimeMs: 1 })
  };
}

describe('research console config', () => {
  it('defaults to in-repo runtime artifact locations', () => {
    const parsed = createResearchConsoleConfig([]);
    expect(parsed.r11AnalysisDir).toBe('research/python/.r11_runtime/analysis');
    expect(parsed.r10RetrievalDir).toBe('.runtime-pipeline/r10-local-retrieval-results');
  });

  it('accepts overridden artifact roots', () => {
    const parsed = createResearchConsoleConfig(['--r11-analysis-dir', '/tmp/a']);
    expect(parsed.r11AnalysisDir).toBe('/tmp/a');
  });
});

describe('research console summary', () => {
  it('reports missing artifact directories instead of failing', async () => {
    const summary = await runResearchConsole(config, runtimeFor({}));
    expect(summary.sources.r11Analysis.exists).toBe(false);
    expect(summary.reviewQueue).toEqual([]);
    expect(summary.coverage.tickersAnalysed).toBe(0);
  });

  it('flags a capital strength verdict resting on equity crossing zero', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'acme.json': analysis({
            ticker: 'ACME.N0000',
            metrics: [
              {
                name: 'group_total_equity_growth',
                value: 198.03,
                current: 508245,
                previous: -518474
              }
            ],
            scorecard: { capital_strength: 'HIGH', manual_review_required: false }
          })
        }
      })
    );

    const entry = summary.reviewQueue.find((item) => item.ticker === 'ACME');
    expect(entry?.integrity.map((finding) => finding.code)).toContain('SIGN_FLIP_DENOMINATOR');
    expect(summary.coverage.integrityFlags).toBe(1);
  });

  it('records the guard holding when equity is negative and unscored', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'hva.json': analysis({
            ticker: 'HVA.N0000',
            metrics: [
              {
                name: 'group_total_equity_growth',
                value: 9.19,
                current: -64290676,
                previous: -70799910
              }
            ],
            scorecard: { capital_strength: null, manual_review_required: true },
            reasons: ['Capital strength was not scored: current group total equity is -64290676.0']
          })
        }
      })
    );

    const entry = summary.reviewQueue.find((item) => item.ticker === 'HVA');
    const finding = entry?.integrity.find((item) => item.code === 'NEGATIVE_EQUITY_UNSCORED');
    expect(finding?.severity).toBe('GUARD_HELD');
    // A held guard is not a flag: it is the system behaving correctly.
    expect(summary.coverage.integrityFlags).toBe(0);
  });

  it('flags a scored balance sheet risk when liabilities exceed assets', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'x.json': analysis({
            ticker: 'HVA.N0000',
            metrics: [
              { name: 'group_total_assets_growth', value: 1, current: 1241119072, previous: 1 },
              { name: 'group_total_liabilities_growth', value: 2, current: 1305409748, previous: 1 }
            ],
            scorecard: { balance_sheet_risk: 'MEDIUM', manual_review_required: true }
          })
        }
      })
    );

    const entry = summary.reviewQueue.find((item) => item.ticker === 'HVA');
    expect(entry?.integrity.map((finding) => finding.code)).toContain('LIABILITIES_EXCEED_ASSETS');
  });

  it('keeps only the newest analysis per ticker', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'old.json': analysis({
            ticker: 'WATA.N0000',
            metrics: [],
            scorecard: { manual_review_required: true },
            generatedAt: '2026-01-01T00:00:00.000Z'
          }),
          'new.json': analysis({
            ticker: 'WATA.N0000',
            metrics: [
              { name: 'group_total_equity_growth', value: 5, current: 10, previous: 9 }
            ],
            scorecard: { manual_review_required: false },
            generatedAt: '2026-08-01T00:00:00.000Z'
          })
        }
      })
    );

    expect(summary.reviewQueue).toHaveLength(1);
    expect(summary.reviewQueue[0]?.state).toBe('CLEAN');
  });

  it('marks an unflagged clean case SETTLED so it does not crowd the queue', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'ael.json': analysis({
            ticker: 'AEL.N0000',
            metrics: [{ name: 'group_total_equity_growth', value: 4, current: 120, previous: 115 }],
            scorecard: { capital_strength: 'MEDIUM', manual_review_required: false }
          })
        }
      })
    );
    expect(summary.reviewQueue[0]?.actionability).toBe('SETTLED');
  });

  it('does not read a missing-metrics list mentioning equity as a capital decision', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        analysis: {
          'rwsl.json': analysis({
            ticker: 'RWSL.N0000',
            metrics: [{ name: 'group_total_assets_growth', value: 3, current: 10, previous: 9 }],
            scorecard: { manual_review_required: true },
            missing: [
              'group_profit_for_the_period_yoy_growth',
              'group_total_liabilities_growth',
              'group_total_equity_growth'
            ],
            reasons: [
              'Missing key aggregated metrics: group_profit_for_the_period_yoy_growth, group_total_liabilities_growth, group_total_equity_growth.'
            ]
          })
        }
      })
    );
    expect(summary.reviewQueue[0]?.actionability).toBe('SOURCE_LIMITED');
  });

  it('separates document-derived retrieval signals from our own annotation', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({
        retrieval: {
          'pkme.json': JSON.stringify({
            query_plan_summary: { ticker: 'PKME.N0000' },
            document_store_path: 'store.jsonl',
            matched_document_count: 1,
            matched_documents: [
              {
                title: 'AGM Circular',
                score: 4.25,
                tickers_hint: ['PKME.N0000'],
                matched_reasons: [
                  'ticker:PKME.N0000',
                  'keyword:PKME',
                  'keyword:DIGITAL MOBILITY SOLUTIONS LANKA'
                ]
              }
            ]
          })
        }
      })
    );

    const doc = summary.retrieval?.documents[0];
    // Only a ticker match can be satisfied by the hint we wrote, so only it is
    // unattributable. Keyword matches fire on the document's own words.
    expect(doc?.annotationDerived).toEqual(['ticker:PKME.N0000']);
    expect(doc?.documentDerived).toEqual([
      'keyword:PKME',
      'keyword:DIGITAL MOBILITY SOLUTIONS LANKA'
    ]);
  });

  it('skips unreadable artifacts rather than reporting them as analysed', async () => {
    const summary = await runResearchConsole(
      config,
      runtimeFor({ analysis: { 'broken.json': '{ not json' } })
    );
    expect(summary.reviewQueue).toEqual([]);
    expect(summary.sources.r11Analysis.exists).toBe(true);
  });
});
