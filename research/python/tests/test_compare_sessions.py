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

from compare_sessions import (  # noqa: E402
    collect_inputs,
    compare_sessions,
    duration_seconds,
    write_csv,
    write_markdown,
)
from summarize_session import SessionFormatError  # noqa: E402


def write_variant_session(tmp_path: Path) -> Path:
    session = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    session["sessionId"] = "sample-atrad-session-variant"
    session["endedAt"] = "2026-05-08T10:17:00.000Z"
    session["snapshots"] = session["snapshots"][:3]
    session["totals"]["usableSnapshots"] = 3
    session["totals"]["quarantinedSnapshots"] = 0
    session["totals"]["rejectedSnapshots"] = 0
    session["diagnostics"] = session["diagnostics"][:2]
    path = tmp_path / "variant-session.json"
    path.write_text(json.dumps(session), encoding="utf-8")
    return path


def test_compares_two_sample_sessions(tmp_path: Path) -> None:
    variant = write_variant_session(tmp_path)

    compared = compare_sessions([str(SAMPLE_PATH), str(variant)], top=3)

    assert [item.summary.session_id for item in compared] == [
        "sample-atrad-session-20260508-101500",
        "sample-atrad-session-variant",
    ]
    assert compared[0].summary.total_snapshots == 5
    assert compared[1].summary.total_snapshots == 3
    assert compared[0].tickers_with_repeated_observations == 1
    assert compared[1].duration_seconds == 120


def test_compare_average_spread_and_quality_notes(tmp_path: Path) -> None:
    variant = write_variant_session(tmp_path)

    compared = compare_sessions([str(variant)], top=3)

    assert compared[0].average_spread_percent == pytest.approx(0.440519, abs=0.000001)
    assert compared[0].data_quality_notes == ["basic quality checks passed"]


def test_compare_writes_markdown_output(tmp_path: Path) -> None:
    output = tmp_path / "compare.md"
    compared = compare_sessions([str(SAMPLE_PATH)])

    write_markdown(compared, output)

    text = output.read_text(encoding="utf-8")
    assert "# Sentinel-CSE Session Comparison" in text
    assert "sample-atrad-session-20260508-101500" in text


def test_compare_writes_csv_output(tmp_path: Path) -> None:
    output = tmp_path / "compare.csv"
    compared = compare_sessions([str(SAMPLE_PATH)])

    write_csv(compared, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
    assert rows[0]["session_id"] == "sample-atrad-session-20260508-101500"
    assert rows[0]["open_ticks"] == "2"


def test_collect_inputs_supports_repeatable_and_comma_separated_values() -> None:
    args = type("Args", (), {"input": ["one.json"], "inputs": ["two.json, three.json"]})()

    assert collect_inputs(args) == ["one.json", "two.json", "three.json"]


def test_collect_inputs_rejects_empty_values() -> None:
    args = type("Args", (), {"input": None, "inputs": [" , "]})()

    with pytest.raises(SessionFormatError, match="At least one"):
        collect_inputs(args)


def test_duration_handles_invalid_or_reversed_dates() -> None:
    assert duration_seconds("not-a-date", "2026-05-08T10:17:00.000Z") == 0
    assert duration_seconds("2026-05-08T10:17:00.000Z", "2026-05-08T10:15:00.000Z") == 0


def test_compare_uses_sample_or_temp_files_only(tmp_path: Path) -> None:
    variant = write_variant_session(tmp_path)
    compared = compare_sessions([str(variant)])
    normalized = str(variant).replace("\\", "/")

    assert compared[0].summary.session_id == "sample-atrad-session-variant"
    assert "/data/live-sessions/" not in normalized
