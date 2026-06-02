from __future__ import annotations

import argparse
import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO

from strategy_blocker_report import build_strategy_blocker_report, load_replay_diagnostics
from summarize_session import SessionFormatError, SessionSummary, load_session, summarize_session
from universe_candidate_report import (
    UniverseCandidateFilters,
    candidate_matches_filters,
    summarize_universe_candidate,
)
from variant_comparison_report import load_variant_comparison

DEFAULT_RUNTIME_DIR = Path(".runtime-pipeline") / "multi-session-validation"
REPLAY_EXPORT_NAME = "replay-diagnostics.json"
VARIANT_EXPORT_NAME = "variant-comparison.json"
EXPECTED_VARIANTS = {
    "baseline": "base",
    "volume-ratio-disabled-diagnostic": "vol-off",
    "imbalance-disabled-diagnostic": "imb-off",
    "volume-and-imbalance-disabled-diagnostic": "both-off",
}


@dataclass(frozen=True)
class AggregateRow:
    session_stem: str
    session_id: str
    coverage_type: str
    quality_classification: str
    ticks_attempted: int | None
    open_ticks: int | None
    total_snapshots: int | None
    unique_tickers: int | None
    scan_mode_summary: str
    coverage_summary: str
    baseline_signals: int | None
    volume_ratio_disabled_signals: int | None
    imbalance_disabled_signals: int | None
    volume_and_imbalance_disabled_signals: int | None
    filtered_baseline_signals: int | None
    filtered_volume_ratio_disabled_signals: int | None
    filtered_imbalance_disabled_signals: int | None
    filtered_volume_and_imbalance_disabled_signals: int | None
    top_blocker: str
    notes: str


@dataclass(frozen=True)
class RuntimeArtifacts:
    replay_path: Path
    variant_path: Path


@dataclass(frozen=True)
class SessionRecord:
    session_stem: str
    session_path: Path | None
    runtime_artifacts: RuntimeArtifacts


@dataclass(frozen=True)
class VariantSignalCounts:
    raw_counts: dict[str, int | None]
    filtered_counts: dict[str, int | None]
    partial: bool = False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a compact multi-session aggregate validation report. "
            "When research-universe filters are active, filtered counts are "
            "report-layer research counts over exported signalTickerCounts only."
        )
    )
    parser.add_argument(
        "--runtime-root",
        default=str(DEFAULT_RUNTIME_DIR),
        help="Runtime output root for multi-session validation exports.",
    )
    parser.add_argument(
        "--input",
        action="append",
        nargs="+",
        help="Optional session JSON path(s). When provided, rows are built from these sessions and enriched from runtime exports when present.",
    )
    parser.add_argument(
        "--exclude-non-voting",
        action="store_true",
        help="Exclude non-voting tickers such as .X0000 from filtered research counts.",
    )
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=[],
        help="Repeatable ticker substring exclusion pattern for filtered research counts.",
    )
    parser.add_argument(
        "--min-snapshots",
        type=int,
        help="Minimum snapshot count required for filtered research counts.",
    )
    parser.add_argument(
        "--min-bid-ask-coverage",
        type=float,
        help="Minimum bid/ask availability ratio required for filtered research counts.",
    )
    parser.add_argument(
        "--max-median-spread",
        type=float,
        help="Maximum median spread percent allowed for filtered research counts.",
    )
    parser.add_argument(
        "--min-latest-turnover",
        type=float,
        help="Minimum latest turnover required for filtered research counts.",
    )
    parser.add_argument(
        "--min-max-volume",
        type=float,
        help="Minimum max volume required for filtered research counts.",
    )
    return parser.parse_args(argv)


def flatten_inputs(values: Iterable[list[str]] | None) -> list[Path]:
    if not values:
        return []
    return [Path(item) for group in values for item in group]


def discover_session_records(runtime_root: Path, input_paths: list[Path]) -> list[SessionRecord]:
    if input_paths:
        ordered_inputs = sorted((Path(path) for path in input_paths), key=session_sort_key_for_path)
        return [
            SessionRecord(
                session_stem=path.stem,
                session_path=path,
                runtime_artifacts=RuntimeArtifacts(
                    replay_path=runtime_root / path.stem / REPLAY_EXPORT_NAME,
                    variant_path=runtime_root / path.stem / VARIANT_EXPORT_NAME,
                ),
            )
            for path in ordered_inputs
        ]

    if not runtime_root.exists():
        return []

    session_dirs = sorted(
        (path for path in runtime_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    return [
        SessionRecord(
            session_stem=session_dir.name,
            session_path=None,
            runtime_artifacts=RuntimeArtifacts(
                replay_path=session_dir / REPLAY_EXPORT_NAME,
                variant_path=session_dir / VARIANT_EXPORT_NAME,
            ),
        )
        for session_dir in session_dirs
    ]


def session_sort_key_for_path(path: Path) -> tuple[str, str]:
    return (path.stem, str(path))


def build_aggregate_rows(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
) -> list[AggregateRow]:
    records = discover_session_records(runtime_root, input_paths)
    resolved_filters = filters or UniverseCandidateFilters()
    return [build_aggregate_row(record, resolved_filters) for record in records]


def build_aggregate_row(
    record: SessionRecord,
    filters: UniverseCandidateFilters,
) -> AggregateRow:
    notes: list[str] = []
    session: dict[str, object] | None = None
    summary: SessionSummary | None = None
    replay_diagnostics: dict[str, object] | None = None
    variant_comparison: dict[str, object] | None = None
    filters_active = filters_are_active(filters)

    if record.runtime_artifacts.replay_path.is_file():
        replay_diagnostics = load_replay_diagnostics(record.runtime_artifacts.replay_path)
    else:
        notes.append("missing replay export")

    if record.runtime_artifacts.variant_path.is_file():
        variant_comparison = load_variant_comparison(record.runtime_artifacts.variant_path)
    else:
        notes.append("missing variant export")

    session_path = record.session_path or infer_session_path(replay_diagnostics, variant_comparison)
    if session_path is not None:
        try:
            session = load_session(session_path)
            summary = summarize_session(session)
        except SessionFormatError:
            notes.append("session JSON unreadable")
    elif replay_diagnostics is not None or variant_comparison is not None:
        notes.append("session JSON unreadable")

    research_universe_pass_map: dict[str, bool] | None = None
    if filters_active:
        if session is None:
            notes.append("filtered counts unavailable")
        else:
            research_universe_pass_map = build_research_universe_pass_map(session, filters)

    blocker_report = (
        build_strategy_blocker_report(replay_diagnostics, top=0)
        if replay_diagnostics is not None
        else None
    )
    variant_counts = extract_variant_counts(
        variant_comparison,
        research_universe_pass_map=research_universe_pass_map,
        filters_active=filters_active,
    )
    if variant_counts.partial:
        notes.append("filtered counts may be partial")

    return AggregateRow(
        session_stem=record.session_stem,
        session_id=resolve_session_id(summary, replay_diagnostics, variant_comparison),
        coverage_type=classify_coverage_type(summary),
        quality_classification=resolve_quality_classification(summary),
        ticks_attempted=summary.ticks_attempted if summary is not None else None,
        open_ticks=summary.quality.open_tick_count if summary is not None else None,
        total_snapshots=resolve_total_snapshots(summary, replay_diagnostics, variant_comparison),
        unique_tickers=resolve_unique_tickers(summary, replay_diagnostics, variant_comparison),
        scan_mode_summary=resolve_scan_mode_summary(summary),
        coverage_summary=resolve_coverage_summary(summary),
        baseline_signals=variant_counts.raw_counts["baseline"],
        volume_ratio_disabled_signals=variant_counts.raw_counts["volume-ratio-disabled-diagnostic"],
        imbalance_disabled_signals=variant_counts.raw_counts["imbalance-disabled-diagnostic"],
        volume_and_imbalance_disabled_signals=variant_counts.raw_counts[
            "volume-and-imbalance-disabled-diagnostic"
        ],
        filtered_baseline_signals=variant_counts.filtered_counts["baseline"],
        filtered_volume_ratio_disabled_signals=variant_counts.filtered_counts[
            "volume-ratio-disabled-diagnostic"
        ],
        filtered_imbalance_disabled_signals=variant_counts.filtered_counts[
            "imbalance-disabled-diagnostic"
        ],
        filtered_volume_and_imbalance_disabled_signals=variant_counts.filtered_counts[
            "volume-and-imbalance-disabled-diagnostic"
        ],
        top_blocker=resolve_top_blocker(replay_diagnostics, blocker_report),
        notes="; ".join(unique_notes(notes)) if notes else "-",
    )


def infer_session_path(
    replay_diagnostics: dict[str, object] | None,
    variant_comparison: dict[str, object] | None,
) -> Path | None:
    for container in (replay_diagnostics, variant_comparison):
        if not isinstance(container, dict):
            continue
        input_path = container.get("inputPath")
        if isinstance(input_path, str) and input_path.strip():
            return Path(input_path)
    return None


def unique_notes(notes: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            ordered.append(note)
    return ordered


def resolve_session_id(
    summary: SessionSummary | None,
    replay_diagnostics: dict[str, object] | None,
    variant_comparison: dict[str, object] | None,
) -> str:
    if summary is not None:
        return summary.session_id
    for container in (replay_diagnostics, variant_comparison):
        if isinstance(container, dict):
            value = container.get("sessionId")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "n/a"


def resolve_quality_classification(summary: SessionSummary | None) -> str:
    if summary is None or summary.quality.classification is None:
        return "unknown"
    return summary.quality.classification


def classify_coverage_type(summary: SessionSummary | None) -> str:
    if summary is None:
        return "unknown"
    dominant_scan_mode = dominant_scan_mode_name(summary)
    median_coverage = summary.quality.median_unique_ticker_coverage
    if dominant_scan_mode == "store_fallback_scroll" and median_coverage is not None and median_coverage >= 400:
        return "strong-full-grid"
    if median_coverage is not None and median_coverage <= 50:
        return "partial-coverage"
    return "unknown"


def dominant_scan_mode_name(summary: SessionSummary) -> str | None:
    if not summary.quality.scan_mode_counts:
        return None
    ordered = sorted(
        summary.quality.scan_mode_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return ordered[0][0]


def resolve_total_snapshots(
    summary: SessionSummary | None,
    replay_diagnostics: dict[str, object] | None,
    variant_comparison: dict[str, object] | None,
) -> int | None:
    if summary is not None:
        return summary.total_snapshots
    for container in (replay_diagnostics, variant_comparison):
        if isinstance(container, dict):
            value = container.get("totalSnapshotsLoaded") or container.get("replayedSnapshots")
            if isinstance(value, int):
                return value
    return None


def resolve_unique_tickers(
    summary: SessionSummary | None,
    replay_diagnostics: dict[str, object] | None,
    variant_comparison: dict[str, object] | None,
) -> int | None:
    if summary is not None:
        return summary.unique_tickers
    for container in (replay_diagnostics, variant_comparison):
        if isinstance(container, dict):
            value = container.get("uniqueTickers")
            if isinstance(value, int):
                return value
    return None


def resolve_scan_mode_summary(summary: SessionSummary | None) -> str:
    if summary is None or not summary.quality.scan_mode_counts:
        return "n/a"
    ordered = sorted(
        summary.quality.scan_mode_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return ", ".join(f"{name}:{count}" for name, count in ordered)


def resolve_coverage_summary(summary: SessionSummary | None) -> str:
    if summary is None:
        return "n/a"
    peak = summary.quality.peak_unique_ticker_coverage
    median_coverage = summary.quality.median_unique_ticker_coverage
    if peak is None or median_coverage is None:
        return "n/a"
    return f"{format_number(peak)}/{format_number(median_coverage)}"


def build_research_universe_pass_map(
    session: dict[str, object],
    filters: UniverseCandidateFilters,
) -> dict[str, bool]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    snapshots = session.get("snapshots")
    if not isinstance(snapshots, list):
        return {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        ticker = snapshot.get("ticker")
        if isinstance(ticker, str) and ticker.strip():
            grouped[ticker.strip()].append(snapshot)
    return {
        ticker: candidate_matches_filters(
            summarize_universe_candidate(ticker, entries),
            filters,
        )
        for ticker, entries in grouped.items()
    }


def extract_variant_counts(
    comparison: dict[str, object] | None,
    *,
    research_universe_pass_map: dict[str, bool] | None,
    filters_active: bool,
) -> VariantSignalCounts:
    raw_counts = {name: None for name in EXPECTED_VARIANTS}
    filtered_counts = {name: None for name in EXPECTED_VARIANTS}
    partial = False
    if not isinstance(comparison, dict):
        return VariantSignalCounts(raw_counts=raw_counts, filtered_counts=filtered_counts)
    variants = comparison.get("variants")
    if not isinstance(variants, list):
        return VariantSignalCounts(raw_counts=raw_counts, filtered_counts=filtered_counts)
    for item in variants:
        if not isinstance(item, dict):
            continue
        variant_name = item.get("variantName")
        if variant_name not in raw_counts:
            continue
        if isinstance(item.get("signalsGenerated"), int):
            raw_counts[variant_name] = int(item["signalsGenerated"])
        if not filters_active:
            continue
        if research_universe_pass_map is None:
            filtered_counts[variant_name] = None
            continue
        signal_ticker_counts = item.get("signalTickerCounts")
        unique_signal_tickers = item.get("uniqueSignalTickers")
        if not isinstance(signal_ticker_counts, list):
            filtered_counts[variant_name] = None
            continue
        filtered_total = 0
        rendered_tickers = 0
        for signal_row in signal_ticker_counts:
            if not isinstance(signal_row, dict):
                continue
            ticker = signal_row.get("ticker")
            count = signal_row.get("count")
            if not isinstance(ticker, str) or not isinstance(count, int):
                continue
            rendered_tickers += 1
            if research_universe_pass_map.get(ticker, False):
                filtered_total += count
        filtered_counts[variant_name] = filtered_total
        if isinstance(unique_signal_tickers, int) and unique_signal_tickers > rendered_tickers:
            partial = True
    return VariantSignalCounts(
        raw_counts=raw_counts,
        filtered_counts=filtered_counts,
        partial=partial,
    )


def resolve_top_blocker(
    replay_diagnostics: dict[str, object] | None,
    blocker_report: object | None,
) -> str:
    if isinstance(replay_diagnostics, dict):
        aggregate = replay_diagnostics.get("aggregateReplayDiagnostics")
        if isinstance(aggregate, dict):
            likely_blockers = aggregate.get("likelyBlockers")
            if isinstance(likely_blockers, list):
                for item in likely_blockers:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
    if blocker_report is not None:
        patterns = getattr(blocker_report, "top_blocker_patterns", [])
        if patterns:
            blocker, _count = patterns[0]
            return blocker
    return "n/a"


def format_number(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return format(value, ".1f").rstrip("0").rstrip(".")


def fit_cell(value: str, width: int) -> str:
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    left_width = max((width - 3) // 2, 1)
    right_width = max(width - 3 - left_width, 1)
    return f"{value[:left_width]}...{value[-right_width:]}".ljust(width)


def format_rows_table(
    rows: list[AggregateRow],
    *,
    show_filtered_columns: bool = False,
) -> str:
    columns = [
        ("session", 24, lambda row: row.session_stem),
        ("sessionId", 24, lambda row: row.session_id),
        ("coverage", 18, lambda row: row.coverage_type),
        ("qual", 7, lambda row: row.quality_classification),
        ("ticks", 7, lambda row: format_number(row.ticks_attempted)),
        ("OPEN", 6, lambda row: format_number(row.open_ticks)),
        ("snaps", 7, lambda row: format_number(row.total_snapshots)),
        ("tickers", 7, lambda row: format_number(row.unique_tickers)),
        ("scan", 30, lambda row: row.scan_mode_summary),
        ("peak/med", 12, lambda row: row.coverage_summary),
        ("base", 6, lambda row: format_number(row.baseline_signals)),
        ("vol-off", 7, lambda row: format_number(row.volume_ratio_disabled_signals)),
        ("imb-off", 7, lambda row: format_number(row.imbalance_disabled_signals)),
        ("both-off", 8, lambda row: format_number(row.volume_and_imbalance_disabled_signals)),
    ]
    if show_filtered_columns:
        columns.extend(
            [
                ("f-base", 6, lambda row: format_number(row.filtered_baseline_signals)),
                ("f-vol", 6, lambda row: format_number(row.filtered_volume_ratio_disabled_signals)),
                ("f-imb", 6, lambda row: format_number(row.filtered_imbalance_disabled_signals)),
                ("f-both", 7, lambda row: format_number(row.filtered_volume_and_imbalance_disabled_signals)),
            ]
        )
    columns.extend(
        [
            ("blocker", 28, lambda row: row.top_blocker),
            ("notes", 30, lambda row: row.notes),
        ]
    )
    header = " ".join(fit_cell(name, width) for name, width, _getter in columns)
    divider = " ".join("-" * width for _name, width, _getter in columns)
    body = [
        " ".join(fit_cell(getter(row), width) for _name, width, getter in columns)
        for row in rows
    ]
    if not body:
        body = ["No sessions found."]
    return "\n".join([header, divider, *body])


def render_report(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
) -> str:
    resolved_filters = filters or UniverseCandidateFilters()
    rows = build_aggregate_rows(runtime_root, input_paths, filters=resolved_filters)
    return format_rows_table(rows, show_filtered_columns=filters_are_active(resolved_filters))


def run_multi_session_aggregate_report(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
    output: TextIO | None = None,
) -> int:
    handle = output or io.StringIO()
    text = render_report(runtime_root, input_paths, filters=filters)
    print(text, file=handle)
    if output is None:
        print(handle.getvalue(), end="")
    return 0


def filters_are_active(filters: UniverseCandidateFilters) -> bool:
    return any(
        (
            filters.exclude_non_voting,
            bool(filters.exclude_patterns),
            filters.min_snapshots is not None,
            filters.min_bid_ask_coverage is not None,
            filters.max_median_spread is not None,
            filters.min_latest_turnover is not None,
            filters.min_max_volume is not None,
        )
    )


def parse_args_and_run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    filters = UniverseCandidateFilters(
        exclude_non_voting=args.exclude_non_voting,
        exclude_patterns=args.exclude_pattern,
        min_snapshots=args.min_snapshots,
        min_bid_ask_coverage=args.min_bid_ask_coverage,
        max_median_spread=args.max_median_spread,
        min_latest_turnover=args.min_latest_turnover,
        min_max_volume=args.min_max_volume,
    )
    return run_multi_session_aggregate_report(
        runtime_root=Path(args.runtime_root),
        input_paths=flatten_inputs(args.input),
        filters=filters,
    )


if __name__ == "__main__":
    raise SystemExit(parse_args_and_run())
