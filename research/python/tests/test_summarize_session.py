from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SAMPLE_PATH = PYTHON_ROOT / "sample_data" / "sample_session.json"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from summarize_session import (  # noqa: E402
    SessionSummary,
    SessionFormatError,
    TickerSummary,
    format_count_like,
    format_percent,
    format_price,
    format_terminal_summary,
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


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def test_rejects_malformed_json() -> None:
    directory = make_temp_dir()
    try:
        malformed = directory / "malformed.json"
        malformed.write_text("{not-json", encoding="utf-8")

        with pytest.raises(SessionFormatError, match="Malformed session JSON"):
            load_session(malformed)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_rejects_missing_required_session_shape() -> None:
    directory = make_temp_dir()
    try:
        malformed = directory / "not-a-session.json"
        malformed.write_text(json.dumps({"snapshots": []}), encoding="utf-8")

        with pytest.raises(SessionFormatError, match="sessionId"):
            load_session(malformed)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


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


def test_writes_markdown_output() -> None:
    directory = make_temp_dir()
    try:
        output = directory / "summary.md"
        summary = summarize_session(load_session(SAMPLE_PATH))

        write_markdown(summary, output)

        text = output.read_text(encoding="utf-8")
        assert "# Sentinel-CSE Session Summary" in text
        assert "| ALFA.N0000 | 3 |" in text
        assert "| ALFA.N0000 | 3 | 0.48 | 41.9 | 41.8 | 42 | 12,000 | 16,000 | 16,000 |" in text
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_writes_csv_output() -> None:
    directory = make_temp_dir()
    try:
        output = directory / "summary.csv"
        summary = summarize_session(load_session(SAMPLE_PATH))

        write_csv(summary, output)

        rows = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
        assert rows[0]["ticker"] == "ALFA.N0000"
        assert rows[0]["snapshot_count"] == "3"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


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


def test_formats_large_volumes_without_scientific_notation() -> None:
    assert format_count_like(77350.0) == "77,350"
    assert format_count_like(985900.0) == "985,900"


def test_formats_prices_cleanly() -> None:
    assert format_price(41.9) == "41.9"
    assert format_price(41.75) == "41.75"
    assert format_price(41.123456) == "41.123456"
    assert format_price(12.12345678) == "12.12345678"


def test_formats_spread_with_two_decimals() -> None:
    assert format_percent(0.478476) == "0.48%"


def test_terminal_summary_uses_human_readable_volume_formatting() -> None:
    summary = summarize_session(load_session(SAMPLE_PATH), top=3)

    text = format_terminal_summary(summary)

    assert "7.735e+" not in text
    assert "volume min/max/latest=12,000/16,000/16,000" in text
    assert "avgSpread=0.48%" in text
    assert "latestLast=41.9" in text


def test_terminal_summary_formats_large_snapshot_counts() -> None:
    summary = SessionSummary(
        session_id="large-count-session",
        started_at="2026-05-08T10:15:00.000Z",
        ended_at="2026-05-08T10:16:00.000Z",
        source="unit-test",
        mode="read-only-local-recording",
        ticks_attempted=1234,
        total_snapshots=1234,
        unique_tickers=1,
        usable_snapshots=1234,
        quarantined_snapshots=0,
        rejected_snapshots=0,
        market_state_counts={"OPEN": 1234, "CLOSED": 0, "INACTIVE": 0, "UNKNOWN": 0},
        top_tickers=[("ALFA.N0000", 1234)],
        ticker_summaries=[
            TickerSummary(
                ticker="ALFA.N0000",
                snapshot_count=1234,
                average_spread_percent=0.478476,
                latest_last_price=12.12345678,
                latest_best_bid=12.12,
                latest_best_ask=12.13,
                volume_min=77350.0,
                volume_max=985900.0,
                volume_latest=985900.0,
            )
        ],
    )

    text = format_terminal_summary(summary)

    assert "total snapshots: 1,234" in text
    assert "- OPEN: 1,234" in text
    assert "snapshots=1,234" in text
    assert "latestLast=12.12345678" in text


def test_markdown_formats_market_state_counts_with_grouping() -> None:
    summary = SessionSummary(
        session_id="market-state-format-session",
        started_at="2026-05-08T10:15:00.000Z",
        ended_at="2026-05-08T10:16:00.000Z",
        source="unit-test",
        mode="read-only-local-recording",
        ticks_attempted=1234,
        total_snapshots=1234,
        unique_tickers=1,
        usable_snapshots=1234,
        quarantined_snapshots=0,
        rejected_snapshots=0,
        market_state_counts={"OPEN": 1234, "CLOSED": 0, "INACTIVE": 0, "UNKNOWN": 0},
        top_tickers=[("ALFA.N0000", 1234)],
        ticker_summaries=[],
    )

    directory = make_temp_dir()
    try:
        output = directory / "summary.md"
        write_markdown(summary, output)
        text = output.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    assert "| OPEN | 1,234 |" in text
    assert "- total snapshots: `1,234`" in text


def test_sample_data_is_not_real_live_sessions_path() -> None:
    normalized = str(SAMPLE_PATH).replace("\\", "/")

    assert "/research/python/sample_data/" in normalized
    assert "/data/live-sessions/" not in normalized
