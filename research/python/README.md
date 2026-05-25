# Sentinel-CSE Python Research Workspace

This folder is for offline analysis of recorded Sentinel-CSE ATrad session JSON files.

The TypeScript runtime remains the source of truth for read-only capture, replay, dashboards, and paper-trading research workflows. Python is intentionally separate and local-only: it reads already-recorded JSON files, produces terminal summaries, and can write Markdown or CSV reports for research review.

## Unofficial CSE Public API Probe

`research/python/scripts/cse_public_api_probe.py` is a research-only probe for unofficial public CSE website endpoints under `https://www.cse.lk/api/`.

- These endpoints are not treated as stable or production-safe APIs.
- Response shapes may change without notice.
- Verify licensing, permission, and acceptable-use expectations with CSE before any production use.
- Do not use this probe for live trading decisions.
- Do not run high-frequency polling or request loops.
- Use one manual request at a time only.

## Safety Boundary

- Do not connect Python scripts to live ATrad.
- Do not automate login or credentials.
- Do not read `.env` files or shell credentials.
- Do not connect Telegram or Supabase.
- Do not place orders or implement auto-trading.
- Do not copy real `data/live-sessions/` files into tracked folders if they contain sensitive data.

## Setup

From the repository root:

```powershell
python -m pip install -r research/python/requirements.txt
```

The first version uses the Python standard library for analysis. `pytest` is included for tests.

The news analyst agent adds a single external dependency: the official `openai` Python SDK, used against DeepSeek by overriding the API base URL.

## Probe Commands

```powershell
python research/python/scripts/cse_public_api_probe.py --endpoint marketStatus --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --summary-only
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --compare-atrad-session data/live-sessions/example.json
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --param page=1 --param size=50 --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --params-json '{"page":1,"size":50}' --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --discover-pagination --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint tradeSummary --compare-atrad-session data/live-sessions/example.json --cross-check-report
```

Probe options:

- `--param KEY=VALUE`: repeatable form-encoded POST body parameter.
- `--params-json '{"page":1,"size":50}'`: JSON object form of request parameters.
- `--discover-pagination`: bounded research-only discovery mode for likely pagination parameter shapes.
- `--cross-check-report`: richer `tradeSummary`-vs-recorded-ATrad validation report with `OK`, `WARN`, `CHECK`, `MISSING_IN_CSE`, and `MISSING_IN_ATRAD` classifications.

Discovery mode is intentionally capped to a small fixed set of attempts, does not retry, and must not be used for high-frequency polling.

For `tradeSummary`, the probe now applies endpoint-specific comparison normalization before matching against a recorded ATrad session: `symbol -> ticker`, `price -> lastPrice`, `sharevolume -> volume`, `turnover -> turnover`, `tradevolume -> trades`, and `lastTradedTime -> timestamp`. Other endpoints still use cautious generic field inference.

Cross-check report thresholds:

- `OK`: price diff <= `0.50%`, volume diff <= `10.00%`, turnover diff <= `10.00%`
- `WARN`: price diff <= `2.00%`, volume diff <= `25.00%`, turnover diff <= `25.00%`
- `CHECK`: larger differences or missing comparable fields

The report always warns that comparisons may be time-shifted unless the public CSE response was captured during the same ATrad recording window. `tradeSummary` does not include bid/ask/depth, so it is only a research cross-check and does not replace ATrad.

## Summarize One Session

```powershell
python research/python/scripts/summarize_session.py --input research/python/sample_data/sample_session.json
```

Optional report outputs:

```powershell
python research/python/scripts/summarize_session.py --input research/python/sample_data/sample_session.json --output-md research/python/reports/sample-summary.md --output-csv research/python/reports/sample-tickers.csv
```

## Compare Sessions

```powershell
python research/python/scripts/compare_sessions.py --input research/python/sample_data/sample_session.json --input research/python/sample_data/sample_session.json
```

Comma-separated input is also supported:

```powershell
python research/python/scripts/compare_sessions.py --inputs research/python/sample_data/sample_session.json,research/python/sample_data/sample_session.json
```

Optional report outputs:

```powershell
python research/python/scripts/compare_sessions.py --input research/python/sample_data/sample_session.json --input research/python/sample_data/sample_session.json --output-md research/python/reports/compare.md --output-csv research/python/reports/compare.csv
```

## R10 News Analyst Agent

The current R10 news analyst lives under `research/python/sentinel_research/agents/` and separates schema validation, provider calls, and orchestration.

R10 is now closed as:

`R10 Foundation + Controlled CBSL/CSE Ingestion + Offline Policy Simulation`

See `research/python/docs/r10_closeout.md` for the final closeout summary, confirmed source boundary, manual runtime paths, safety constraints, and known limitations.

Manual runtime smoke test only:

```powershell
$env:DEEPSEEK_API_KEY="your-key"
python research/python/scripts/test_r10_agent.py
```

This smoke test is for manual execution only after setting `DEEPSEEK_API_KEY`. It is not run by `pytest` or CI.

## R11 Institutional Financial Analyst Layer

R11 is planned/starting as the Institutional Financial Analyst layer. It builds on R10-verified official CBSL/CSE documents and metadata, with R10 supplying the source boundary for future financial table extraction, accounting normalization, deterministic calculations, and strict analyst dossiers.

See `research/python/docs/r11_architecture.md` for the R11 architecture document.

See `research/python/docs/r11_tools_datasets_matrix.md` for the R11 tools and datasets evaluation matrix.

See `research/python/docs/r11_teaching_from_finance_resources.md` for the R11 teaching strategy from external finance resources.

See `research/python/docs/r11_table_extraction_bakeoff.md` for the R11 table extraction bakeoff design.

The initial R11.1 schema foundation now lives under `research/python/sentinel_research/agents/r11/`.

The initial R11.2 calculation toolbox now lives under `research/python/sentinel_research/agents/r11/tools/`.

The initial R11.3B `pypdf` baseline extraction adapter now lives under `research/python/sentinel_research/agents/r11/extraction/`.

The initial R11.3E statement page locator now lives under `research/python/sentinel_research/agents/r11/extraction/statement_locator.py`.

The initial R11.3F prototype `pypdf` financial row parser now lives under `research/python/sentinel_research/agents/r11/extraction/pypdf_row_parser.py`.

The initial R11.4A line-item normalization foundation now lives under `research/python/sentinel_research/agents/r11/tables/`.

The initial R11.4C column/period mapping and numeric string parsing foundation now lives under `research/python/sentinel_research/agents/r11/tables/value_mapper.py`.

## Reports

Generated reports belong in `research/python/reports/`. The directory is kept with `.gitkeep`; generated report files are ignored by Git.

## Tests

```powershell
python -m pytest research/python/tests
```
