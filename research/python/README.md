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

## Probe Commands

```powershell
python research/python/scripts/cse_public_api_probe.py --endpoint marketStatus --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --summary-only
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --compare-atrad-session data/live-sessions/example.json
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --param page=1 --param size=50 --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --params-json '{"page":1,"size":50}' --dry-run
python research/python/scripts/cse_public_api_probe.py --endpoint todaySharePrice --discover-pagination --dry-run
```

Probe options:

- `--param KEY=VALUE`: repeatable form-encoded POST body parameter.
- `--params-json '{"page":1,"size":50}'`: JSON object form of request parameters.
- `--discover-pagination`: bounded research-only discovery mode for likely pagination parameter shapes.

Discovery mode is intentionally capped to a small fixed set of attempts, does not retry, and must not be used for high-frequency polling.

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

## Reports

Generated reports belong in `research/python/reports/`. The directory is kept with `.gitkeep`; generated report files are ignored by Git.

## Tests

```powershell
python -m pytest research/python/tests
```
