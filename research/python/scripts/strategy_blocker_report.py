from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

FUNNEL_FIELDS = (
    "snapshots",
    "historyPass",
    "strategyReady",
    "spreadPass",
    "vwapAvailable",
    "priceAboveVwap",
    "firstHighAvailable",
    "momentumPass",
    "volumeRatioAvailable",
    "volumeRatioPass",
    "imbalanceAvailable",
    "imbalancePass",
    "signals",
)

AGGREGATE_FIELDS = (
    "spreadBlockedCount",
    "volumeBlockedCount",
    "imbalanceBlockedCount",
    "vwapMissingCount",
    "firstFiveMinuteHighMissingCount",
    "priceNotAboveVwapCount",
    "priceNotAboveMomentumTriggerCount",
    "insufficientHistoryCount",
    "strategyReadySnapshotCount",
)


class ReplayDiagnosticsFormatError(ValueError):
    """Raised when an input file is not a replay diagnostics JSON export."""


@dataclass(frozen=True)
class PerTickerConditionDiagnostic:
    ticker: str
    snapshots: int | None = None
    history_pass: int | None = None
    strategy_ready: int | None = None
    spread_pass: int | None = None
    vwap_available: int | None = None
    price_above_vwap: int | None = None
    first_high_available: int | None = None
    momentum_pass: int | None = None
    volume_ratio_available: int | None = None
    volume_ratio_pass: int | None = None
    imbalance_available: int | None = None
    imbalance_pass: int | None = None
    signals: int | None = None
    top_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyBlockerReport:
    session_id: str | None
    input_path: str | None
    source: str | None
    replayed_snapshots: int | None
    unique_tickers: int | None
    signals_generated: int | None
    threshold_summary: dict[str, str | int | float | None]
    aggregate_blockers: dict[str, int | list[str] | None]
    condition_funnel: dict[str, int | None]
    top_blocker_patterns: list[tuple[str, int]]
    momentum_candidates: list[PerTickerConditionDiagnostic]
    volume_ratio_candidates: list[PerTickerConditionDiagnostic]
    top_limit: int | None = None
    per_ticker_available: bool = False


def load_replay_diagnostics(path: str | Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ReplayDiagnosticsFormatError(
            f"Unable to read replay diagnostics file: {path}. {error}"
        ) from error

    try:
        diagnostics = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReplayDiagnosticsFormatError(
            f"Malformed replay diagnostics JSON: {error}"
        ) from error

    validate_replay_diagnostics(diagnostics)
    return diagnostics


def validate_replay_diagnostics(diagnostics: Any) -> None:
    if not isinstance(diagnostics, dict):
        raise ReplayDiagnosticsFormatError("Replay diagnostics root must be an object.")


def build_strategy_blocker_report(
    diagnostics: dict[str, Any],
    top: int | None = 10,
) -> StrategyBlockerReport:
    threshold_summary = diagnostics.get("thresholdSummary")
    aggregate_blockers = diagnostics.get("aggregateReplayDiagnostics")
    raw_per_ticker = diagnostics.get("perTickerConditionDiagnostics")
    per_ticker_rows = parse_per_ticker_rows(raw_per_ticker)
    safe_top = max(top, 0) if top is not None else None

    return StrategyBlockerReport(
        session_id=optional_string(diagnostics.get("sessionId")),
        input_path=optional_string(diagnostics.get("inputPath")),
        source=optional_string(diagnostics.get("source")),
        replayed_snapshots=optional_int(diagnostics.get("replayedSnapshots")),
        unique_tickers=optional_int(diagnostics.get("uniqueTickers")),
        signals_generated=optional_int(diagnostics.get("signalsGenerated")),
        threshold_summary={
            "maxSpreadPercent": optional_number(threshold_summary, "maxSpreadPercent"),
            "minimumVolumeRatio": optional_number(threshold_summary, "minimumVolumeRatio"),
            "minimumImbalance": optional_number(threshold_summary, "minimumImbalance"),
            "momentumTriggerBasis": optional_nested_string(
                threshold_summary, "momentumTriggerBasis"
            ),
        },
        aggregate_blockers={
            **{
                field: optional_number(aggregate_blockers, field)
                for field in AGGREGATE_FIELDS
            },
            "likelyBlockers": optional_string_list(aggregate_blockers, "likelyBlockers"),
        },
        condition_funnel=aggregate_condition_funnel(per_ticker_rows),
        top_blocker_patterns=aggregate_top_blocker_patterns(per_ticker_rows),
        momentum_candidates=identify_momentum_candidates(per_ticker_rows, safe_top),
        volume_ratio_candidates=identify_volume_ratio_candidates(per_ticker_rows, safe_top),
        top_limit=safe_top,
        per_ticker_available=isinstance(raw_per_ticker, list),
    )


def parse_per_ticker_rows(value: Any) -> list[PerTickerConditionDiagnostic]:
    if not isinstance(value, list):
        return []

    rows: list[PerTickerConditionDiagnostic] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ticker = optional_string(item.get("ticker"))
        if ticker is None:
            continue
        rows.append(
            PerTickerConditionDiagnostic(
                ticker=ticker,
                snapshots=optional_int(item.get("snapshots")),
                history_pass=optional_int(item.get("historyPass")),
                strategy_ready=optional_int(item.get("strategyReady")),
                spread_pass=optional_int(item.get("spreadPass")),
                vwap_available=optional_int(item.get("vwapAvailable")),
                price_above_vwap=optional_int(item.get("priceAboveVwap")),
                first_high_available=optional_int(item.get("firstHighAvailable")),
                momentum_pass=optional_int(item.get("momentumPass")),
                volume_ratio_available=optional_int(item.get("volumeRatioAvailable")),
                volume_ratio_pass=optional_int(item.get("volumeRatioPass")),
                imbalance_available=optional_int(item.get("imbalanceAvailable")),
                imbalance_pass=optional_int(item.get("imbalancePass")),
                signals=optional_int(item.get("signals")),
                top_blockers=tuple(parse_top_blockers(item.get("topBlockers"))),
            )
        )
    return rows


def aggregate_condition_funnel(
    rows: list[PerTickerConditionDiagnostic],
) -> dict[str, int | None]:
    if not rows:
        return {field: None for field in FUNNEL_FIELDS}

    field_values: dict[str, list[int]] = {field: [] for field in FUNNEL_FIELDS}
    for row in rows:
        values = {
            "snapshots": row.snapshots,
            "historyPass": row.history_pass,
            "strategyReady": row.strategy_ready,
            "spreadPass": row.spread_pass,
            "vwapAvailable": row.vwap_available,
            "priceAboveVwap": row.price_above_vwap,
            "firstHighAvailable": row.first_high_available,
            "momentumPass": row.momentum_pass,
            "volumeRatioAvailable": row.volume_ratio_available,
            "volumeRatioPass": row.volume_ratio_pass,
            "imbalanceAvailable": row.imbalance_available,
            "imbalancePass": row.imbalance_pass,
            "signals": row.signals,
        }
        for field, field_value in values.items():
            if field_value is not None:
                field_values[field].append(field_value)

    totals: dict[str, int | None] = {}
    for field in FUNNEL_FIELDS:
        values = field_values[field]
        totals[field] = sum(values) if len(values) == len(rows) else None
    return totals


def aggregate_top_blocker_patterns(
    rows: list[PerTickerConditionDiagnostic],
) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        for blocker in row.top_blockers:
            counts[blocker] += 1
    return counts.most_common()


def identify_momentum_candidates(
    rows: list[PerTickerConditionDiagnostic],
    top: int | None,
) -> list[PerTickerConditionDiagnostic]:
    candidates = [
        row
        for row in rows
        if row.snapshots is not None
        and row.snapshots > 0
        and "momentum trigger blocked" in row.top_blockers
        and row.spread_pass == row.snapshots
        and row.vwap_available == row.snapshots
        and row.price_above_vwap == row.snapshots
        and row.imbalance_available == row.snapshots
        and row.imbalance_pass == row.imbalance_available
        and row.first_high_available is not None
        and row.momentum_pass is not None
        and row.first_high_available > row.momentum_pass
    ]
    ordered = sorted(candidates, key=momentum_candidate_sort_key)
    return ordered[:top] if top is not None else ordered


def identify_volume_ratio_candidates(
    rows: list[PerTickerConditionDiagnostic],
    top: int | None,
) -> list[PerTickerConditionDiagnostic]:
    candidates = [
        row
        for row in rows
        if row.snapshots is not None
        and row.snapshots > 0
        and "volume ratio blocked" in row.top_blockers
        and row.spread_pass == row.snapshots
        and row.vwap_available == row.snapshots
        and row.price_above_vwap == row.snapshots
        and row.imbalance_available == row.snapshots
        and row.imbalance_pass == row.imbalance_available
        and row.first_high_available is not None
        and row.momentum_pass is not None
        and row.momentum_pass > 0
        and row.volume_ratio_available is not None
        and row.volume_ratio_pass is not None
        and row.volume_ratio_available > row.volume_ratio_pass
    ]
    ordered = sorted(candidates, key=volume_ratio_candidate_sort_key)
    return ordered[:top] if top is not None else ordered


def momentum_candidate_sort_key(
    candidate: PerTickerConditionDiagnostic,
) -> tuple[int, int, int, str]:
    momentum_gap = (candidate.first_high_available or 0) - (candidate.momentum_pass or 0)
    other_blockers = sum(1 for blocker in candidate.top_blockers if blocker != "momentum trigger blocked")
    return (
        other_blockers,
        -momentum_gap,
        -(candidate.snapshots or 0),
        candidate.ticker,
    )


def volume_ratio_candidate_sort_key(
    candidate: PerTickerConditionDiagnostic,
) -> tuple[int, int, int, str]:
    volume_gap = (candidate.volume_ratio_available or 0) - (candidate.volume_ratio_pass or 0)
    other_blockers = sum(1 for blocker in candidate.top_blockers if blocker != "volume ratio blocked")
    return (
        other_blockers,
        -volume_gap,
        -(candidate.snapshots or 0),
        candidate.ticker,
    )


def format_strategy_blocker_report(report: StrategyBlockerReport) -> str:
    lines = [
        "Sentinel-CSE strategy blocker report",
        f"sessionId: {format_optional_string(report.session_id)}",
        f"inputPath: {format_optional_string(report.input_path)}",
        f"source: {format_optional_string(report.source)}",
        f"replayedSnapshots: {format_optional_number(report.replayed_snapshots)}",
        f"uniqueTickers: {format_optional_number(report.unique_tickers)}",
        f"signalsGenerated: {format_optional_number(report.signals_generated)}",
        f"top limit: {format_optional_number(report.top_limit)}",
        "",
        "Threshold summary:",
        f"- maxSpreadPercent: {format_optional_decimal(report.threshold_summary['maxSpreadPercent'])}",
        f"- minimumVolumeRatio: {format_optional_decimal(report.threshold_summary['minimumVolumeRatio'])}",
        f"- minimumImbalance: {format_optional_decimal(report.threshold_summary['minimumImbalance'])}",
        f"- momentumTriggerBasis: {format_optional_string(report.threshold_summary['momentumTriggerBasis'])}",
        "",
        "Aggregate blocker summary:",
        *[
            f"- {field}: {format_optional_number(report.aggregate_blockers[field])}"
            for field in AGGREGATE_FIELDS
        ],
        f"- likelyBlockers: {format_string_list(report.aggregate_blockers.get('likelyBlockers'))}",
        "",
        "Condition funnel:",
        *[
            f"- {field}: {format_optional_number(report.condition_funnel[field])}"
            for field in FUNNEL_FIELDS
        ],
        "",
        "Top blocker patterns:",
    ]

    if report.top_blocker_patterns:
        lines.extend(
            f"- {pattern}: {format_optional_number(count)}"
            for pattern, count in report.top_blocker_patterns
        )
    else:
        lines.append("- unavailable")

    lines.extend(
        [
            "",
            "Near-pass tickers:",
            "- fails mainly momentum:",
        ]
    )
    if report.momentum_candidates:
        lines.extend(format_candidate_line(candidate, "momentum") for candidate in report.momentum_candidates)
    else:
        lines.append("- unavailable")

    lines.append("- fails mainly volume ratio:")
    if report.volume_ratio_candidates:
        lines.extend(
            format_candidate_line(candidate, "volume ratio")
            for candidate in report.volume_ratio_candidates
        )
    else:
        lines.append("- unavailable")

    return "\n".join(lines)


def format_candidate_line(
    candidate: PerTickerConditionDiagnostic,
    focus: str,
) -> str:
    focus_value = (
        format_ratio_pair(candidate.momentum_pass, candidate.first_high_available)
        if focus == "momentum"
        else format_ratio_pair(candidate.volume_ratio_pass, candidate.volume_ratio_available)
    )
    focus_label = "momentumPass" if focus == "momentum" else "volumeRatioPass"
    return (
        f"- {candidate.ticker} | snapshots={format_optional_number(candidate.snapshots)}"
        f" | spreadPass={format_ratio_pair(candidate.spread_pass, candidate.snapshots)}"
        f" | priceAboveVwap={format_ratio_pair(candidate.price_above_vwap, candidate.snapshots)}"
        f" | imbalancePass={format_ratio_pair(candidate.imbalance_pass, candidate.imbalance_available)}"
        f" | {focus_label}={focus_value}"
        f" | topBlockers={format_string_list(list(candidate.top_blockers))}"
    )


def parse_top_blockers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    blockers: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            blockers.append(item.strip())
    return blockers


def optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_nested_string(container: Any, field: str) -> str | None:
    if not isinstance(container, dict):
        return None
    return optional_string(container.get(field))


def optional_string_list(container: Any, field: str) -> list[str] | None:
    if not isinstance(container, dict):
        return None
    value = container.get(field)
    if not isinstance(value, list):
        return None
    parsed = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return parsed or None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit() or (
            stripped.startswith("-") and stripped[1:].isdigit()
        ):
            try:
                return int(stripped)
            except ValueError:
                return None
    return None


def optional_number(container: Any, field: str) -> int | float | None:
    if not isinstance(container, dict):
        return None
    value = container.get(field)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            decimal_value = Decimal(value.strip())
        except Exception:
            return None
        if decimal_value == decimal_value.quantize(Decimal("1")):
            return int(decimal_value)
        return float(decimal_value)
    return None


def format_optional_string(value: Any) -> str:
    if value is None:
        return "unavailable"
    return str(value)


def format_optional_number(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        decimal_value = Decimal(str(value))
        if decimal_value == decimal_value.quantize(Decimal("1")):
            return f"{int(decimal_value):,}"
        return format(decimal_value.normalize(), "f").rstrip("0").rstrip(".")
    return str(value)


def format_optional_decimal(value: Any) -> str:
    return format_optional_number(value)


def format_string_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "unavailable"
    return ", ".join(str(value) for value in values)


def format_ratio_pair(passed: int | None, total: int | None) -> str:
    if passed is None or total is None:
        return "unavailable"
    return f"{passed}/{total}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize strategy blockers from one exported Sentinel-CSE replay diagnostics JSON file."
    )
    parser.add_argument("--input", required=True, help="Path to a replay diagnostics JSON file.")
    parser.add_argument("--top", type=int, default=10, help="Number of near-pass tickers to display.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        diagnostics = load_replay_diagnostics(Path(args.input))
        report = build_strategy_blocker_report(diagnostics, top=max(args.top, 0))
        print(format_strategy_blocker_report(report))
        return 0
    except ReplayDiagnosticsFormatError as error:
        print(f"Strategy blocker report failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
