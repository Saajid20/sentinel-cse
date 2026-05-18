from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MARKET_STATES = ("OPEN", "CLOSED", "INACTIVE", "UNKNOWN")


class SessionFormatError(ValueError):
    """Raised when an input file is not a Sentinel-CSE recorded session."""


@dataclass(frozen=True)
class TickerSummary:
    ticker: str
    snapshot_count: int
    average_spread_percent: float | None
    latest_last_price: float | None
    latest_best_bid: float | None
    latest_best_ask: float | None
    volume_min: float | None
    volume_max: float | None
    volume_latest: float | None


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    started_at: str
    ended_at: str
    source: str
    mode: str
    ticks_attempted: int | None
    total_snapshots: int
    unique_tickers: int
    usable_snapshots: int | None
    quarantined_snapshots: int | None
    rejected_snapshots: int | None
    market_state_counts: dict[str, int]
    top_tickers: list[tuple[str, int]]
    ticker_summaries: list[TickerSummary]


def load_session(path: str | Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise SessionFormatError(f"Unable to read session file: {path}. {error}") from error

    try:
        session = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SessionFormatError(f"Malformed session JSON: {error}") from error

    validate_session(session)
    return session


def validate_session(session: Any) -> None:
    if not isinstance(session, dict):
        raise SessionFormatError("Session root must be an object.")

    for key in ("sessionId", "startedAt", "endedAt", "source", "mode"):
        if not isinstance(session.get(key), str) or not session[key].strip():
            raise SessionFormatError(f"Session field {key} must be a non-empty string.")

    if "snapshots" not in session or not isinstance(session["snapshots"], list):
        raise SessionFormatError("Session field snapshots must be an array.")

    if "diagnostics" in session and not isinstance(session["diagnostics"], list):
        raise SessionFormatError("Session field diagnostics must be an array when present.")

    if "totals" in session and not isinstance(session["totals"], dict):
        raise SessionFormatError("Session field totals must be an object when present.")


def summarize_session(session: dict[str, Any], top: int = 10) -> SessionSummary:
    snapshots = [snapshot for snapshot in session.get("snapshots", []) if isinstance(snapshot, dict)]
    totals = session.get("totals") if isinstance(session.get("totals"), dict) else {}
    ticker_counts = Counter(
        snapshot.get("ticker")
        for snapshot in snapshots
        if isinstance(snapshot.get("ticker"), str) and snapshot.get("ticker")
    )

    ticker_summaries = summarize_tickers(snapshots)

    return SessionSummary(
        session_id=session["sessionId"],
        started_at=session["startedAt"],
        ended_at=session["endedAt"],
        source=session["source"],
        mode=session["mode"],
        ticks_attempted=optional_int(totals.get("ticksAttempted")),
        total_snapshots=len(snapshots),
        unique_tickers=len(ticker_counts),
        usable_snapshots=optional_int(totals.get("usableSnapshots")),
        quarantined_snapshots=optional_int(totals.get("quarantinedSnapshots")),
        rejected_snapshots=optional_int(totals.get("rejectedSnapshots")),
        market_state_counts=market_state_counts(session.get("diagnostics", [])),
        top_tickers=ticker_counts.most_common(max(top, 0)),
        ticker_summaries=ticker_summaries[: max(top, 0)],
    )


def summarize_tickers(snapshots: list[dict[str, Any]]) -> list[TickerSummary]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        ticker = snapshot.get("ticker")
        if isinstance(ticker, str) and ticker:
            grouped[ticker].append(snapshot)

    summaries: list[TickerSummary] = []
    for ticker, entries in grouped.items():
        ordered = sorted(entries, key=lambda entry: numeric_value(entry.get("timestamp")) or 0)
        latest = ordered[-1]
        spreads = [
            spread
            for spread in (spread_percent(entry) for entry in ordered)
            if spread is not None
        ]
        volumes = [
            volume
            for volume in (numeric_value(entry.get("volume")) for entry in ordered)
            if volume is not None
        ]
        summaries.append(
            TickerSummary(
                ticker=ticker,
                snapshot_count=len(entries),
                average_spread_percent=average(spreads),
                latest_last_price=numeric_value(latest.get("lastPrice")),
                latest_best_bid=numeric_value(latest.get("bestBid")),
                latest_best_ask=numeric_value(latest.get("bestAsk")),
                volume_min=min(volumes) if volumes else None,
                volume_max=max(volumes) if volumes else None,
                volume_latest=numeric_value(latest.get("volume")),
            )
        )

    return sorted(summaries, key=lambda item: (-item.snapshot_count, item.ticker))


def market_state_counts(diagnostics: Any) -> dict[str, int]:
    counts = {state: 0 for state in MARKET_STATES}
    if not isinstance(diagnostics, list):
        return counts

    for diagnostic in diagnostics:
        state = diagnostic.get("marketState") if isinstance(diagnostic, dict) else None
        counts[state if state in counts else "UNKNOWN"] += 1

    return counts


def spread_percent(snapshot: dict[str, Any]) -> float | None:
    bid = numeric_value(snapshot.get("bestBid"))
    ask = numeric_value(snapshot.get("bestAsk"))
    if bid is None or ask is None or ask <= 0:
        return None
    return ((ask - bid) / ask) * 100


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def format_terminal_summary(summary: SessionSummary) -> str:
    lines = [
        "Sentinel-CSE recorded session summary",
        f"sessionId: {summary.session_id}",
        f"startedAt: {summary.started_at}",
        f"endedAt: {summary.ended_at}",
        f"source: {summary.source}",
        f"mode: {summary.mode}",
        f"ticks attempted: {format_optional(summary.ticks_attempted)}",
        f"total snapshots: {summary.total_snapshots}",
        f"unique tickers: {summary.unique_tickers}",
        f"usable/quarantined/rejected: {format_optional(summary.usable_snapshots)}/{format_optional(summary.quarantined_snapshots)}/{format_optional(summary.rejected_snapshots)}",
        "market states:",
        *[f"- {state}: {summary.market_state_counts[state]}" for state in MARKET_STATES],
        "top tickers:",
    ]
    lines.extend(f"- {ticker}: {count}" for ticker, count in summary.top_tickers)
    if not summary.top_tickers:
        lines.append("- none")

    lines.append("per-ticker details:")
    for item in summary.ticker_summaries:
        lines.append(
            f"- {item.ticker}: snapshots={item.snapshot_count}, avgSpread={format_percent(item.average_spread_percent)}, "
            f"latestLast={format_optional_number(item.latest_last_price)}, latestBidAsk={format_optional_number(item.latest_best_bid)}/{format_optional_number(item.latest_best_ask)}, "
            f"volume min/max/latest={format_optional_number(item.volume_min)}/{format_optional_number(item.volume_max)}/{format_optional_number(item.volume_latest)}"
        )
    if not summary.ticker_summaries:
        lines.append("- none")

    return "\n".join(lines)


def write_markdown(summary: SessionSummary, path: str | Path) -> None:
    lines = [
        f"# Sentinel-CSE Session Summary: {summary.session_id}",
        "",
        f"- startedAt: `{summary.started_at}`",
        f"- endedAt: `{summary.ended_at}`",
        f"- source: `{summary.source}`",
        f"- mode: `{summary.mode}`",
        f"- ticks attempted: `{format_optional(summary.ticks_attempted)}`",
        f"- total snapshots: `{summary.total_snapshots}`",
        f"- unique tickers: `{summary.unique_tickers}`",
        f"- usable/quarantined/rejected: `{format_optional(summary.usable_snapshots)}/{format_optional(summary.quarantined_snapshots)}/{format_optional(summary.rejected_snapshots)}`",
        "",
        "## Market States",
        "",
        "| State | Ticks |",
        "|---|---:|",
        *[f"| {state} | {summary.market_state_counts[state]} |" for state in MARKET_STATES],
        "",
        "## Tickers",
        "",
        "| Ticker | Snapshots | Avg Spread % | Latest Last | Latest Bid | Latest Ask | Volume Min | Volume Max | Volume Latest |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(markdown_ticker_row(item) for item in summary.ticker_summaries)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(summary: SessionSummary, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker",
                "snapshot_count",
                "average_spread_percent",
                "latest_last_price",
                "latest_best_bid",
                "latest_best_ask",
                "volume_min",
                "volume_max",
                "volume_latest",
            ],
        )
        writer.writeheader()
        for item in summary.ticker_summaries:
            writer.writerow(
                {
                    "ticker": item.ticker,
                    "snapshot_count": item.snapshot_count,
                    "average_spread_percent": item.average_spread_percent,
                    "latest_last_price": item.latest_last_price,
                    "latest_best_bid": item.latest_best_bid,
                    "latest_best_ask": item.latest_best_ask,
                    "volume_min": item.volume_min,
                    "volume_max": item.volume_max,
                    "volume_latest": item.volume_latest,
                }
            )


def markdown_ticker_row(item: TickerSummary) -> str:
    return (
        f"| {item.ticker} | {item.snapshot_count} | {format_optional_number(item.average_spread_percent)} | "
        f"{format_optional_number(item.latest_last_price)} | {format_optional_number(item.latest_best_bid)} | "
        f"{format_optional_number(item.latest_best_ask)} | {format_optional_number(item.volume_min)} | "
        f"{format_optional_number(item.volume_max)} | {format_optional_number(item.volume_latest)} |"
    )


def format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def format_optional(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def format_optional_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a recorded Sentinel-CSE ATrad session JSON file.")
    parser.add_argument("--input", required=True, help="Path to a recorded session JSON file.")
    parser.add_argument("--output-md", help="Optional Markdown report output path.")
    parser.add_argument("--output-csv", help="Optional per-ticker CSV output path.")
    parser.add_argument("--top", type=int, default=10, help="Number of top ticker rows to include.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        session = load_session(args.input)
        summary = summarize_session(session, top=args.top)
        if args.output_md:
            write_markdown(summary, args.output_md)
        if args.output_csv:
            write_csv(summary, args.output_csv)
        print(format_terminal_summary(summary))
        return 0
    except SessionFormatError as error:
        print(f"Session summary failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
