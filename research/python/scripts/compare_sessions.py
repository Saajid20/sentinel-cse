from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from summarize_session import (
    SessionFormatError,
    SessionSummary,
    average,
    format_optional,
    format_optional_number,
    format_percent,
    load_session,
    spread_percent,
    summarize_session,
)


@dataclass(frozen=True)
class ComparedSession:
    input_path: str
    summary: SessionSummary
    duration_seconds: int
    tickers_with_repeated_observations: int
    average_spread_percent: float | None
    top_repeated_tickers: list[tuple[str, int]]
    data_quality_notes: list[str]


def compare_sessions(paths: list[str], top: int = 10) -> list[ComparedSession]:
    compared: list[ComparedSession] = []
    for path in paths:
        session = load_session(path)
        summary = summarize_session(session, top=top)
        snapshots = [snapshot for snapshot in session.get("snapshots", []) if isinstance(snapshot, dict)]
        spreads = [spread for spread in (spread_percent(snapshot) for snapshot in snapshots) if spread is not None]
        repeated = [(ticker, count) for ticker, count in summary.top_tickers if count >= 2]
        compared.append(
            ComparedSession(
                input_path=path,
                summary=summary,
                duration_seconds=duration_seconds(summary.started_at, summary.ended_at),
                tickers_with_repeated_observations=len(repeated),
                average_spread_percent=average(spreads),
                top_repeated_tickers=repeated[: max(top, 0)],
                data_quality_notes=build_data_quality_notes(summary, repeated),
            )
        )
    return compared


def build_data_quality_notes(summary: SessionSummary, repeated: list[tuple[str, int]]) -> list[str]:
    notes: list[str] = []
    if summary.total_snapshots == 0:
        notes.append("no snapshots")
    if not repeated:
        notes.append("no repeated ticker observations")
    if summary.market_state_counts["OPEN"] == 0 and sum(summary.market_state_counts.values()) > 0:
        notes.append("no OPEN ticks")
    if summary.rejected_snapshots and summary.usable_snapshots is not None and summary.rejected_snapshots > summary.usable_snapshots:
        notes.append("rejected snapshots exceed usable snapshots")
    if not notes:
        notes.append("basic quality checks passed")
    return notes


def duration_seconds(started_at: str, ended_at: str) -> int:
    try:
        start = parse_iso_datetime(started_at)
        end = parse_iso_datetime(ended_at)
    except ValueError:
        return 0
    seconds = int((end - start).total_seconds())
    return max(seconds, 0)


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_terminal_comparison(compared: list[ComparedSession]) -> str:
    lines = [
        "Sentinel-CSE recorded session comparison",
        f"sessions compared: {len(compared)}",
        "",
    ]
    for index, item in enumerate(compared, start=1):
        summary = item.summary
        lines.extend(
            [
                f"{index}. {summary.session_id}",
                f"   input: {item.input_path}",
                f"   duration seconds: {item.duration_seconds}",
                f"   total snapshots: {summary.total_snapshots}",
                f"   unique tickers: {summary.unique_tickers}",
                f"   usable/quarantined/rejected: {format_optional(summary.usable_snapshots)}/{format_optional(summary.quarantined_snapshots)}/{format_optional(summary.rejected_snapshots)}",
                f"   OPEN/CLOSED/INACTIVE/UNKNOWN: {summary.market_state_counts['OPEN']}/{summary.market_state_counts['CLOSED']}/{summary.market_state_counts['INACTIVE']}/{summary.market_state_counts['UNKNOWN']}",
                f"   tickers with repeated observations: {item.tickers_with_repeated_observations}",
                f"   average spread: {format_percent(item.average_spread_percent)}",
                f"   top repeated tickers: {format_repeated_tickers(item.top_repeated_tickers)}",
                f"   data quality notes: {'; '.join(item.data_quality_notes)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def write_markdown(compared: list[ComparedSession], path: str | Path) -> None:
    lines = [
        "# Sentinel-CSE Session Comparison",
        "",
        "| Session | Duration Seconds | Snapshots | Unique Tickers | Usable | Quarantined | Rejected | Open Ticks | Closed Ticks | Inactive Ticks | Unknown Ticks | Repeated Tickers | Avg Spread % | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines.extend(markdown_row(item) for item in compared)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(compared: list[ComparedSession], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "input_path",
                "session_id",
                "duration_seconds",
                "total_snapshots",
                "unique_tickers",
                "usable_snapshots",
                "quarantined_snapshots",
                "rejected_snapshots",
                "open_ticks",
                "closed_ticks",
                "inactive_ticks",
                "unknown_ticks",
                "tickers_with_repeated_observations",
                "average_spread_percent",
                "top_repeated_tickers",
                "data_quality_notes",
            ],
        )
        writer.writeheader()
        for item in compared:
            summary = item.summary
            writer.writerow(
                {
                    "input_path": item.input_path,
                    "session_id": summary.session_id,
                    "duration_seconds": item.duration_seconds,
                    "total_snapshots": summary.total_snapshots,
                    "unique_tickers": summary.unique_tickers,
                    "usable_snapshots": summary.usable_snapshots,
                    "quarantined_snapshots": summary.quarantined_snapshots,
                    "rejected_snapshots": summary.rejected_snapshots,
                    "open_ticks": summary.market_state_counts["OPEN"],
                    "closed_ticks": summary.market_state_counts["CLOSED"],
                    "inactive_ticks": summary.market_state_counts["INACTIVE"],
                    "unknown_ticks": summary.market_state_counts["UNKNOWN"],
                    "tickers_with_repeated_observations": item.tickers_with_repeated_observations,
                    "average_spread_percent": item.average_spread_percent,
                    "top_repeated_tickers": format_repeated_tickers(item.top_repeated_tickers),
                    "data_quality_notes": "; ".join(item.data_quality_notes),
                }
            )


def markdown_row(item: ComparedSession) -> str:
    summary = item.summary
    return (
        f"| {summary.session_id} | {item.duration_seconds} | {summary.total_snapshots} | {summary.unique_tickers} | "
        f"{format_optional(summary.usable_snapshots)} | {format_optional(summary.quarantined_snapshots)} | {format_optional(summary.rejected_snapshots)} | "
        f"{summary.market_state_counts['OPEN']} | {summary.market_state_counts['CLOSED']} | {summary.market_state_counts['INACTIVE']} | {summary.market_state_counts['UNKNOWN']} | "
        f"{item.tickers_with_repeated_observations} | {format_optional_number(item.average_spread_percent)} | {'; '.join(item.data_quality_notes)} |"
    )


def format_repeated_tickers(values: list[tuple[str, int]]) -> str:
    return "none" if not values else ", ".join(f"{ticker}:{count}" for ticker, count in values)


def collect_inputs(args: argparse.Namespace) -> list[str]:
    inputs: list[str] = []
    for value in args.input or []:
        if value.strip():
            inputs.append(value.strip())
    for group in args.inputs or []:
        inputs.extend(value.strip() for value in group.split(",") if value.strip())
    if not inputs:
        raise SessionFormatError("At least one --input or --inputs value is required.")
    return inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare recorded Sentinel-CSE ATrad session JSON files.")
    parser.add_argument("--input", action="append", help="Path to a recorded session JSON file. Repeatable.")
    parser.add_argument("--inputs", action="append", help="Comma-separated session JSON paths.")
    parser.add_argument("--output-md", help="Optional Markdown report output path.")
    parser.add_argument("--output-csv", help="Optional comparison CSV output path.")
    parser.add_argument("--top", type=int, default=10, help="Number of top repeated ticker rows to include.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = collect_inputs(args)
        compared = compare_sessions(paths, top=args.top)
        if args.output_md:
            write_markdown(compared, args.output_md)
        if args.output_csv:
            write_csv(compared, args.output_csv)
        print(format_terminal_comparison(compared))
        return 0
    except SessionFormatError as error:
        print(f"Session comparison failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
