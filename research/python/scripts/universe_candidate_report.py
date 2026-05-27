from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from summarize_session import SessionFormatError, load_session, numeric_value, spread_percent


@dataclass(frozen=True)
class UniverseCandidate:
    ticker: str
    company_name: str | None
    snapshot_count: int
    bid_ask_available_count: int
    bid_ask_coverage_ratio: float
    average_spread_percent: float | None
    median_spread_percent: float | None
    latest_last_price: float | None
    latest_best_bid: float | None
    latest_best_ask: float | None
    latest_volume: float | None
    max_volume: float | None
    latest_turnover: float | None
    max_turnover: float | None
    quality_status_counts: dict[str, int]


@dataclass(frozen=True)
class UniverseCandidateReport:
    session_id: str
    started_at: str
    ended_at: str
    source: str
    mode: str
    total_snapshots: int
    unique_tickers: int
    candidates: list[UniverseCandidate]


def build_universe_candidate_report(
    session: dict[str, Any],
    top: int | None = None,
) -> UniverseCandidateReport:
    snapshots = [snapshot for snapshot in session.get("snapshots", []) if isinstance(snapshot, dict)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        ticker = snapshot.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            grouped[ticker.strip()].append(snapshot)

    candidates = sorted(
        (summarize_universe_candidate(ticker, entries) for ticker, entries in grouped.items()),
        key=universe_candidate_sort_key,
    )
    if top is not None and top >= 0:
        candidates = candidates[:top]

    return UniverseCandidateReport(
        session_id=session["sessionId"],
        started_at=session["startedAt"],
        ended_at=session["endedAt"],
        source=session["source"],
        mode=session["mode"],
        total_snapshots=len(snapshots),
        unique_tickers=len(grouped),
        candidates=candidates,
    )


def summarize_universe_candidate(
    ticker: str,
    snapshots: list[dict[str, Any]],
) -> UniverseCandidate:
    ordered = sorted(snapshots, key=lambda snapshot: numeric_value(snapshot.get("timestamp")) or 0)
    latest = ordered[-1]
    spreads = [spread for spread in (spread_percent(snapshot) for snapshot in ordered) if spread is not None]
    bid_ask_available_count = sum(1 for snapshot in ordered if has_valid_bid_ask(snapshot))
    volumes = [volume for volume in (numeric_value(snapshot.get("volume")) for snapshot in ordered) if volume is not None]
    turnovers = [
        turnover for turnover in (numeric_value(snapshot.get("totalTurnover")) for snapshot in ordered) if turnover is not None
    ]
    quality_status_counts = Counter()
    company_name = latest_company_name(ordered)
    for snapshot in ordered:
        quality_status = read_quality_status(snapshot)
        if quality_status is not None:
            quality_status_counts[quality_status] += 1

    return UniverseCandidate(
        ticker=ticker,
        company_name=company_name,
        snapshot_count=len(ordered),
        bid_ask_available_count=bid_ask_available_count,
        bid_ask_coverage_ratio=(
            bid_ask_available_count / len(ordered) if ordered else 0.0
        ),
        average_spread_percent=(sum(spreads) / len(spreads)) if spreads else None,
        median_spread_percent=float(median(spreads)) if spreads else None,
        latest_last_price=numeric_value(latest.get("lastPrice")),
        latest_best_bid=numeric_value(latest.get("bestBid")),
        latest_best_ask=numeric_value(latest.get("bestAsk")),
        latest_volume=numeric_value(latest.get("volume")),
        max_volume=max(volumes) if volumes else None,
        latest_turnover=numeric_value(latest.get("totalTurnover")),
        max_turnover=max(turnovers) if turnovers else None,
        quality_status_counts=dict(
            sorted(quality_status_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
    )


def universe_candidate_sort_key(candidate: UniverseCandidate) -> tuple[float, float, float, float, str]:
    median_spread = candidate.median_spread_percent if candidate.median_spread_percent is not None else float("inf")
    latest_turnover = candidate.latest_turnover if candidate.latest_turnover is not None else float("-inf")
    return (
        -candidate.snapshot_count,
        -candidate.bid_ask_coverage_ratio,
        median_spread,
        -latest_turnover,
        candidate.ticker,
    )


def has_valid_bid_ask(snapshot: dict[str, Any]) -> bool:
    bid = numeric_value(snapshot.get("bestBid"))
    ask = numeric_value(snapshot.get("bestAsk"))
    return bid is not None and ask is not None and ask > 0


def latest_company_name(snapshots: list[dict[str, Any]]) -> str | None:
    for snapshot in reversed(snapshots):
        metadata = snapshot.get("metadata")
        if isinstance(metadata, dict):
            company_name = metadata.get("companyName")
            if isinstance(company_name, str) and company_name.strip():
                return company_name.strip()
    return None


def read_quality_status(snapshot: dict[str, Any]) -> str | None:
    metadata = snapshot.get("metadata")
    if not isinstance(metadata, dict):
        return None
    quality_status = metadata.get("qualityStatus")
    if not isinstance(quality_status, str) or not quality_status.strip():
        return None
    return quality_status.strip().upper()


def format_universe_candidate_report(report: UniverseCandidateReport) -> str:
    rows = [
        [
            str(index),
            candidate.ticker,
            truncate(candidate.company_name or "unavailable", 24),
            format_int(candidate.snapshot_count),
            format_int(candidate.bid_ask_available_count),
            format_ratio(candidate.bid_ask_coverage_ratio),
            format_percent(candidate.average_spread_percent),
            format_percent(candidate.median_spread_percent),
            format_number(candidate.latest_last_price),
            format_number(candidate.latest_best_bid),
            format_number(candidate.latest_best_ask),
            format_number(candidate.latest_volume),
            format_number(candidate.max_volume),
            format_number(candidate.latest_turnover),
            format_number(candidate.max_turnover),
            format_quality_breakdown(candidate.quality_status_counts),
        ]
        for index, candidate in enumerate(report.candidates, start=1)
    ]
    headers = [
        "Rank",
        "Ticker",
        "Company",
        "Snapshots",
        "BidAsk",
        "BidAsk%",
        "AvgSpr%",
        "MedSpr%",
        "Last",
        "Bid",
        "Ask",
        "LatestVol",
        "MaxVol",
        "LatestTurn",
        "MaxTurn",
        "Quality",
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rows)) if rows else len(header)
        for index, header in enumerate(headers)
    ]

    lines = [
        "Sentinel-CSE universe candidate report",
        f"sessionId: {report.session_id}",
        f"startedAt: {report.started_at}",
        f"endedAt: {report.ended_at}",
        f"source: {report.source}",
        f"mode: {report.mode}",
        f"total snapshots: {format_int(report.total_snapshots)}",
        f"unique tickers: {format_int(report.unique_tickers)}",
        f"ranked candidates: {format_int(len(report.candidates))}",
        "",
        format_table_row(headers, widths),
        format_table_row(["-" * width for width in widths], widths),
    ]

    if rows:
        lines.extend(format_table_row(row, widths) for row in rows)
    else:
        lines.append("No ticker candidates found.")

    return "\n".join(lines)


def format_table_row(values: list[str], widths: list[int]) -> str:
    return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))


def format_quality_breakdown(values: dict[str, int]) -> str:
    if not values:
        return "unavailable"
    return ", ".join(f"{status}:{count}" for status, count in values.items())


def truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def format_ratio(value: float | None) -> str:
    return "unavailable" if value is None else f"{value * 100:.2f}%"


def format_percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.2f}%"


def format_int(value: int) -> str:
    return f"{value:,}"


def format_number(value: float | None) -> str:
    if value is None:
        return "unavailable"
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.quantize(Decimal("1")):
        return f"{int(decimal_value):,}"
    return format(decimal_value.normalize(), "f").rstrip("0").rstrip(".")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank universe candidates from one recorded Sentinel-CSE ATrad session JSON file."
    )
    parser.add_argument("--input", required=True, help="Path to a recorded session JSON file.")
    parser.add_argument("--top", type=int, default=25, help="Number of ranked tickers to display.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        session = load_session(Path(args.input))
        report = build_universe_candidate_report(session, top=max(args.top, 0))
        print(format_universe_candidate_report(report))
        return 0
    except SessionFormatError as error:
        print(f"Universe candidate report failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
