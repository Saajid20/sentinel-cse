from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SAMPLE_PATH = PYTHON_ROOT / "sample_data" / "sample_session.json"
sys.path.insert(0, str(SCRIPTS_DIR))

from summarize_session import (  # noqa: E402
    SessionFormatError,
    load_session,
    market_state_counts,
    spread_percent,
    summarize_session,
    write_csv,
    write_markdown,
)


def test_loads_valid_sample_session() -> None:
    session = load_session(SAMPLE_PATH)

    assert session["sessionId"] == "sample-atrad-session-20260508-101500"
    assert session["mode"] == "read-only-local-recording"


def test_rejects_malformed_json(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SessionFormatError, match="Malformed session JSON"):
        load_session(malformed)


def test_rejects_missing_required_session_shape(tmp_path: Path) -> None:
    malformed = tmp_path / "not-a-session.json"
    malformed.write_text(json.dumps({"snapshots": []}), encoding="utf-8")

    with pytest.raises(SessionFormatError, match="sessionId"):
        load_session(malformed)


def test_summarizes_tickers_and_top_counts() -> None:
    summary = summarize_session(load_session(SAMPLE_PATH), top=2)

    assert summary.total_snapshots == 5
    assert summary.unique_tickers == 3
    assert summary.top_tickers == [("ALFA.N0000", 3), ("BETA.N0000", 1)]
    assert [item.ticker for item in summary.ticker_summaries] == ["ALFA.N0000", "BETA.N0000"]


def test_calculates_market_state_counts() -> None:
    session = load_session(SAMPLE_PATH)

    assert market_state_counts(session["diagnostics"]) == {
        "OPEN": 2,
        "CLOSED": 0,
        "INACTIVE": 1,
        "UNKNOWN": 1,
    }


def test_calculates_average_spread_percent() -> None:
    summary = summarize_session(load_session(SAMPLE_PATH), top=10)
    alfa = next(item for item in summary.ticker_summaries if item.ticker == "ALFA.N0000")

    assert spread_percent({"bestBid": 41.4, "bestAsk": 41.6}) == pytest.approx(0.480769, abs=0.000001)
    assert alfa.average_spread_percent == pytest.approx(0.478476, abs=0.000001)


def test_writes_markdown_output(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"
    summary = summarize_session(load_session(SAMPLE_PATH))

    write_markdown(summary, output)

    text = output.read_text(encoding="utf-8")
    assert "# Sentinel-CSE Session Summary" in text
    assert "| ALFA.N0000 | 3 |" in text


def test_writes_csv_output(tmp_path: Path) -> None:
    output = tmp_path / "summary.csv"
    summary = summarize_session(load_session(SAMPLE_PATH))

    write_csv(summary, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
    assert rows[0]["ticker"] == "ALFA.N0000"
    assert rows[0]["snapshot_count"] == "3"


def test_handles_missing_optional_fields_gracefully() -> None:
    session = {
        "sessionId": "minimal-session",
        "startedAt": "2026-05-08T10:15:00.000Z",
        "endedAt": "2026-05-08T10:16:00.000Z",
        "source": "unit-test",
        "mode": "read-only-local-recording",
        "snapshots": [{"ticker": "MIN.N0000", "lastPrice": 10.0}],
    }

    summary = summarize_session(session)

    assert summary.ticks_attempted is None
    assert summary.usable_snapshots is None
    assert summary.market_state_counts["UNKNOWN"] == 0
    assert summary.ticker_summaries[0].average_spread_percent is None


def test_sample_data_is_not_real_live_sessions_path() -> None:
    normalized = str(SAMPLE_PATH).replace("\\", "/")

    assert "/research/python/sample_data/" in normalized
    assert "/data/live-sessions/" not in normalized
