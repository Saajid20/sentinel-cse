from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from statistics import median
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
class SessionQualitySummary:
    classification: str | None = None
    classification_reason: str | None = None
    training_grade_count: int | None = None
    training_grade_ratio: float | None = None
    training_grade_evaluated_ticks: int = 0
    scan_mode_counts: dict[str, int] = field(default_factory=dict)
    full_grid_scan_yes_count: int | None = None
    full_grid_scan_no_count: int | None = None
    peak_unique_ticker_coverage: int | None = None
    median_unique_ticker_coverage: float | None = None
    top_rejection_reasons: list[tuple[str, int]] = field(default_factory=list)
    usable_snapshots: int | None = None
    quarantined_snapshots: int | None = None
    rejected_snapshots: int | None = None
    rejection_ratio: float | None = None
    observed_tick_count: int = 0
    open_tick_count: int = 0
    open_tick_ratio: float | None = None


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
    quality: SessionQualitySummary = field(default_factory=SessionQualitySummary)


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
    diagnostics = session.get("diagnostics", [])
    ticker_counts = Counter(
        snapshot.get("ticker")
        for snapshot in snapshots
        if isinstance(snapshot.get("ticker"), str) and snapshot.get("ticker")
    )

    ticker_summaries = summarize_tickers(snapshots)
    state_counts = market_state_counts(diagnostics)
    usable_snapshots = optional_int(totals.get("usableSnapshots"))
    quarantined_snapshots = optional_int(totals.get("quarantinedSnapshots"))
    rejected_snapshots = optional_int(totals.get("rejectedSnapshots"))

    return SessionSummary(
        session_id=session["sessionId"],
        started_at=session["startedAt"],
        ended_at=session["endedAt"],
        source=session["source"],
        mode=session["mode"],
        ticks_attempted=optional_int(totals.get("ticksAttempted")),
        total_snapshots=len(snapshots),
        unique_tickers=len(ticker_counts),
        usable_snapshots=usable_snapshots,
        quarantined_snapshots=quarantined_snapshots,
        rejected_snapshots=rejected_snapshots,
        market_state_counts=state_counts,
        top_tickers=ticker_counts.most_common(max(top, 0)),
        ticker_summaries=ticker_summaries[: max(top, 0)],
        quality=summarize_session_quality(
            diagnostics,
            totals,
            state_counts,
            usable_snapshots,
            quarantined_snapshots,
            rejected_snapshots,
        ),
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


def summarize_session_quality(
    diagnostics: Any,
    totals: dict[str, Any],
    state_counts: dict[str, int],
    usable_snapshots: int | None,
    quarantined_snapshots: int | None,
    rejected_snapshots: int | None,
) -> SessionQualitySummary:
    if not isinstance(diagnostics, list):
        diagnostics = []

    diagnostic_rows = [item for item in diagnostics if isinstance(item, dict)]
    observed_tick_count = len(diagnostic_rows)
    open_tick_count = state_counts["OPEN"]
    open_tick_ratio = (
        open_tick_count / observed_tick_count if observed_tick_count > 0 else None
    )

    training_grade_values = [
        parsed
        for parsed in (
            parse_yes_no_field(row.get("trainingGradeCandidate")) for row in diagnostic_rows
        )
        if parsed is not None
    ]
    training_grade_count = (
        sum(1 for value in training_grade_values if value) if training_grade_values else None
    )
    training_grade_ratio = (
        (training_grade_count / len(training_grade_values))
        if training_grade_count is not None and training_grade_values
        else None
    )

    scan_mode_counts = Counter(
        row.get("scanMode")
        for row in diagnostic_rows
        if isinstance(row.get("scanMode"), str) and row.get("scanMode")
    )

    full_grid_values = [
        value
        for value in (row.get("fullGridScan") for row in diagnostic_rows)
        if isinstance(value, bool)
    ]
    full_grid_scan_yes_count = (
        sum(1 for value in full_grid_values if value) if full_grid_values else None
    )
    full_grid_scan_no_count = (
        sum(1 for value in full_grid_values if not value) if full_grid_values else None
    )

    unique_ticker_values = [
        value
        for value in (
            optional_int(row.get("uniqueTickers")) for row in diagnostic_rows
        )
        if value is not None
    ]
    peak_unique_ticker_coverage = max(unique_ticker_values) if unique_ticker_values else None
    median_unique_ticker_coverage = (
        float(median(unique_ticker_values)) if unique_ticker_values else None
    )

    rejection_counts: Counter[str] = Counter()
    for row in diagnostic_rows:
        top_reject_reasons = row.get("topRejectReasons")
        if not isinstance(top_reject_reasons, list):
            continue
        for entry in top_reject_reasons:
            if not isinstance(entry, dict):
                continue
            code = entry.get("code")
            count = optional_int(entry.get("count"))
            if isinstance(code, str) and code and count is not None and count > 0:
                rejection_counts[code] += count

    if usable_snapshots is None:
        usable_snapshots = aggregate_diagnostic_total(diagnostic_rows, "usableSnapshots")
    if quarantined_snapshots is None:
        quarantined_snapshots = aggregate_diagnostic_total(
            diagnostic_rows, "quarantinedSnapshots"
        )
    if rejected_snapshots is None:
        rejected_snapshots = aggregate_diagnostic_total(diagnostic_rows, "rejectedSnapshots")

    rejection_ratio = calculate_rejection_ratio(
        usable_snapshots,
        quarantined_snapshots,
        rejected_snapshots,
    )

    quality_fields_available = any(
        (
            training_grade_values,
            scan_mode_counts,
            full_grid_values,
            unique_ticker_values,
            rejection_counts,
            usable_snapshots is not None,
            quarantined_snapshots is not None,
            rejected_snapshots is not None,
        )
    )
    classification, classification_reason = classify_session_quality(
        quality_fields_available=quality_fields_available,
        observed_tick_count=observed_tick_count,
        open_tick_count=open_tick_count,
        open_tick_ratio=open_tick_ratio,
        usable_snapshots=usable_snapshots,
        full_grid_scan_yes_count=full_grid_scan_yes_count,
        peak_unique_ticker_coverage=peak_unique_ticker_coverage,
        rejection_ratio=rejection_ratio,
        training_grade_evaluated_ticks=len(training_grade_values),
        training_grade_count=training_grade_count,
    )

    return SessionQualitySummary(
        classification=classification,
        classification_reason=classification_reason,
        training_grade_count=training_grade_count,
        training_grade_ratio=training_grade_ratio,
        training_grade_evaluated_ticks=len(training_grade_values),
        scan_mode_counts=dict(scan_mode_counts),
        full_grid_scan_yes_count=full_grid_scan_yes_count,
        full_grid_scan_no_count=full_grid_scan_no_count,
        peak_unique_ticker_coverage=peak_unique_ticker_coverage,
        median_unique_ticker_coverage=median_unique_ticker_coverage,
        top_rejection_reasons=rejection_counts.most_common(5),
        usable_snapshots=usable_snapshots,
        quarantined_snapshots=quarantined_snapshots,
        rejected_snapshots=rejected_snapshots,
        rejection_ratio=rejection_ratio,
        observed_tick_count=observed_tick_count,
        open_tick_count=open_tick_count,
        open_tick_ratio=open_tick_ratio,
    )


def aggregate_diagnostic_total(
    diagnostics: list[dict[str, Any]],
    field_name: str,
) -> int | None:
    values = [
        value
        for value in (optional_int(row.get(field_name)) for row in diagnostics)
        if value is not None
    ]
    return sum(values) if values else None


def classify_session_quality(
    *,
    quality_fields_available: bool,
    observed_tick_count: int,
    open_tick_count: int,
    open_tick_ratio: float | None,
    usable_snapshots: int | None,
    full_grid_scan_yes_count: int | None,
    peak_unique_ticker_coverage: int | None,
    rejection_ratio: float | None,
    training_grade_evaluated_ticks: int,
    training_grade_count: int | None,
) -> tuple[str | None, str | None]:
    if observed_tick_count == 0 or not quality_fields_available:
        return None, None

    if open_tick_count == 0:
        return "FAIL", "no OPEN ticks recorded"

    if usable_snapshots is not None and usable_snapshots <= 0:
        return "FAIL", "no usable snapshots recorded"

    issues: list[str] = []
    strengths: list[str] = []

    if open_tick_ratio is not None:
        if open_tick_ratio >= 0.5:
            strengths.append("OPEN market coverage is strong")
        else:
            issues.append("OPEN market coverage is mixed")

    if full_grid_scan_yes_count is not None and observed_tick_count > 0:
        full_grid_scan_ratio = full_grid_scan_yes_count / observed_tick_count
        if full_grid_scan_ratio >= 0.5:
            strengths.append("full-grid scan coverage is strong")
        else:
            issues.append("full-grid scan coverage is limited")

    if peak_unique_ticker_coverage is not None:
        if peak_unique_ticker_coverage >= 25:
            strengths.append("unique ticker coverage is broad")
        else:
            issues.append("unique ticker coverage is limited")

    if rejection_ratio is not None:
        if rejection_ratio <= 0.5:
            strengths.append("rejection ratio is controlled")
        else:
            issues.append("rejection ratio is high")

    if training_grade_evaluated_ticks > 0:
        if training_grade_count is not None and training_grade_count > 0:
            strengths.append("training-grade ticks were recorded")
        else:
            issues.append("no training-grade ticks recorded")

    if usable_snapshots is not None and usable_snapshots > 0:
        strengths.append("usable snapshots were recorded")

    if not issues and strengths:
        return "PASS", summarize_quality_reason(strengths[:3])

    if issues:
        return "WARN", summarize_quality_reason(issues[:2])

    return "WARN", "quality diagnostics are partial"


def summarize_quality_reason(reasons: list[str]) -> str:
    if not reasons:
        return "quality diagnostics are partial"
    if len(reasons) == 1:
        return reasons[0]
    return "; ".join(reasons)


def calculate_rejection_ratio(
    usable_snapshots: int | None,
    quarantined_snapshots: int | None,
    rejected_snapshots: int | None,
) -> float | None:
    components = [usable_snapshots, quarantined_snapshots, rejected_snapshots]
    if any(value is None for value in components):
        return None

    denominator = sum(value for value in components if value is not None)
    if denominator <= 0 or rejected_snapshots is None:
        return None

    return rejected_snapshots / denominator


def parse_yes_no_field(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


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
        f"total snapshots: {format_optional(summary.total_snapshots)}",
        f"unique tickers: {format_optional(summary.unique_tickers)}",
        f"usable/quarantined/rejected: {format_optional(summary.usable_snapshots)}/{format_optional(summary.quarantined_snapshots)}/{format_optional(summary.rejected_snapshots)}",
        "market states:",
        *[f"- {state}: {format_optional(summary.market_state_counts[state])}" for state in MARKET_STATES],
        "session quality:",
        f"- classification: {format_quality_classification(summary.quality)}",
        f"- training-grade ticks: {format_quality_ratio(summary.quality.training_grade_count, summary.quality.training_grade_evaluated_ticks, summary.quality.training_grade_ratio)}",
        f"- scan modes: {format_distribution(summary.quality.scan_mode_counts)}",
        f"- full-grid scan yes/no: {format_yes_no_counts(summary.quality.full_grid_scan_yes_count, summary.quality.full_grid_scan_no_count)}",
        f"- unique ticker coverage peak/median: {format_optional(summary.quality.peak_unique_ticker_coverage)}/{format_optional_number(summary.quality.median_unique_ticker_coverage)}",
        f"- top rejection reasons: {format_top_rejection_reasons(summary.quality.top_rejection_reasons)}",
        f"- quality usable/quarantined/rejected: {format_optional(summary.quality.usable_snapshots)}/{format_optional(summary.quality.quarantined_snapshots)}/{format_optional(summary.quality.rejected_snapshots)}",
        f"- market-state quality: {format_market_state_quality(summary.quality)}",
        "top tickers:",
    ]
    lines.extend(f"- {ticker}: {format_optional(count)}" for ticker, count in summary.top_tickers)
    if not summary.top_tickers:
        lines.append("- none")

    lines.append("per-ticker details:")
    for item in summary.ticker_summaries:
        lines.append(
            f"- {item.ticker}: snapshots={format_optional(item.snapshot_count)}, avgSpread={format_percent(item.average_spread_percent)}, "
            f"latestLast={format_price(item.latest_last_price)}, latestBidAsk={format_price(item.latest_best_bid)}/{format_price(item.latest_best_ask)}, "
            f"volume min/max/latest={format_count_like(item.volume_min)}/{format_count_like(item.volume_max)}/{format_count_like(item.volume_latest)}"
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
        f"- total snapshots: `{format_optional(summary.total_snapshots)}`",
        f"- unique tickers: `{format_optional(summary.unique_tickers)}`",
        f"- usable/quarantined/rejected: `{format_optional(summary.usable_snapshots)}/{format_optional(summary.quarantined_snapshots)}/{format_optional(summary.rejected_snapshots)}`",
        "",
        "## Market States",
        "",
        "| State | Ticks |",
        "|---|---:|",
        *[f"| {state} | {format_optional(summary.market_state_counts[state])} |" for state in MARKET_STATES],
        "",
        "## Session Quality",
        "",
        f"- classification: `{format_quality_classification(summary.quality)}`",
        f"- training-grade ticks: `{format_quality_ratio(summary.quality.training_grade_count, summary.quality.training_grade_evaluated_ticks, summary.quality.training_grade_ratio)}`",
        f"- scan modes: `{format_distribution(summary.quality.scan_mode_counts)}`",
        f"- full-grid scan yes/no: `{format_yes_no_counts(summary.quality.full_grid_scan_yes_count, summary.quality.full_grid_scan_no_count)}`",
        f"- unique ticker coverage peak/median: `{format_optional(summary.quality.peak_unique_ticker_coverage)}/{format_optional_number(summary.quality.median_unique_ticker_coverage)}`",
        f"- top rejection reasons: `{format_top_rejection_reasons(summary.quality.top_rejection_reasons)}`",
        f"- quality usable/quarantined/rejected: `{format_optional(summary.quality.usable_snapshots)}/{format_optional(summary.quality.quarantined_snapshots)}/{format_optional(summary.quality.rejected_snapshots)}`",
        f"- market-state quality: `{format_market_state_quality(summary.quality)}`",
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
        f"| {item.ticker} | {format_optional(item.snapshot_count)} | {format_percent_value(item.average_spread_percent)} | "
        f"{format_price(item.latest_last_price)} | {format_price(item.latest_best_bid)} | "
        f"{format_price(item.latest_best_ask)} | {format_count_like(item.volume_min)} | "
        f"{format_count_like(item.volume_max)} | {format_count_like(item.volume_latest)} |"
    )


def format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def format_percent_value(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def format_optional(value: int | None) -> str:
    return "n/a" if value is None else f"{value:,}"


def format_price(value: float | None) -> str:
    if value is None:
        return "n/a"
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.quantize(Decimal("0.01")):
        return format_decimal(decimal_value, grouping=True)
    return format_decimal(decimal_value.normalize(), grouping=True)


def format_count_like(value: float | None) -> str:
    if value is None:
        return "n/a"
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.quantize(Decimal("1")):
        return format_decimal(decimal_value.quantize(Decimal("1")), grouping=True)
    return format_decimal(decimal_value.quantize(Decimal("0.0001")).normalize(), grouping=True)


def format_number(value: float, max_decimals: int, grouping: bool) -> str:
    prefix = "," if grouping else ""
    formatted = format(value, f"{prefix}.{max_decimals}f")
    if "." not in formatted:
        return formatted
    trimmed = formatted.rstrip("0").rstrip(".")
    return "0" if trimmed in {"", "-0"} else trimmed


def format_decimal(value: Decimal, grouping: bool) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    sign = ""
    if text.startswith("-"):
        sign = "-"
        text = text[1:]
    integer_part, _, fractional_part = text.partition(".")
    if grouping:
        integer_part = f"{int(integer_part):,}"
    return f"{sign}{integer_part}.{fractional_part}" if fractional_part else f"{sign}{integer_part}"


def format_optional_number(value: float | None) -> str:
    return "n/a" if value is None else format_number(value, max_decimals=6, grouping=False)


def format_quality_classification(quality: SessionQualitySummary) -> str:
    if quality.classification is None:
        return "unavailable"
    if quality.classification_reason:
        return f"{quality.classification} ({quality.classification_reason})"
    return quality.classification


def format_quality_ratio(
    count: int | None,
    denominator: int,
    ratio: float | None,
) -> str:
    if count is None or denominator <= 0 or ratio is None:
        return "unavailable"
    return f"{format_optional(count)}/{format_optional(denominator)} ({format_percent(ratio * 100)})"


def format_distribution(values: dict[str, int]) -> str:
    if not values:
        return "unavailable"
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name}:{format_optional(count)}" for name, count in ordered)


def format_yes_no_counts(yes_count: int | None, no_count: int | None) -> str:
    if yes_count is None or no_count is None:
        return "unavailable"
    return f"{format_optional(yes_count)}/{format_optional(no_count)}"


def format_top_rejection_reasons(values: list[tuple[str, int]]) -> str:
    if not values:
        return "unavailable"
    return ", ".join(f"{code}:{format_optional(count)}" for code, count in values)


def format_market_state_quality(quality: SessionQualitySummary) -> str:
    if quality.observed_tick_count <= 0 or quality.open_tick_ratio is None:
        return "unavailable"
    return (
        f"OPEN {format_optional(quality.open_tick_count)}/{format_optional(quality.observed_tick_count)} "
        f"({format_percent(quality.open_tick_ratio * 100)})"
    )


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
