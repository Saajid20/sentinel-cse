# Sentinel-CSE Python Research Workspace

This folder is for offline analysis of recorded Sentinel-CSE ATrad session JSON files.

The TypeScript runtime remains the source of truth for read-only capture, replay, dashboards, and paper-trading research workflows. Python is intentionally separate and local-only: it reads already-recorded JSON files, produces terminal summaries, and can write Markdown or CSV reports for research review.

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
