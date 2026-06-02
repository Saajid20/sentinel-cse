from __future__ import annotations

import argparse
import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO

from summarize_session import SessionFormatError, SessionSummary, load_session, summarize_session
from universe_candidate_report import (
    UniverseCandidate,
    UniverseCandidateFilters,
    candidate_matches_filters,
    summarize_universe_candidate,
)
from variant_comparison_report import load_variant_comparison

DEFAULT_RUNTIME_DIR = Path(".runtime-pipeline") / "multi-session-validation"
VARIANT_EXPORT_NAME = "variant-comparison.json"
EXPECTED_VARIANTS = {
    "baseline": "base",
    "volume-ratio-disabled-diagnostic": "vol-off",
    "imbalance-disabled-diagnostic": "imb-off",
    "volume-and-imbalance-disabled-diagnostic": "both-off",
}
VARIANT_LABEL_ORDER = ["base", "vol-off", "imb-off", "both-off"]


@dataclass(frozen=True)
class RuntimeArtifacts:
    variant_path: Path


@dataclass(frozen=True)
class SessionRecord:
    session_stem: str
    session_path: Path | None
    runtime_artifacts: RuntimeArtifacts


@dataclass(frozen=True)
class SessionContext:
    session_stem: str
    session_id: str
    session_path: Path | None
    coverage_type: str
    summary: SessionSummary | None
    candidates: dict[str, UniverseCandidate] | None


@dataclass(frozen=True)
class DetailRow:
    session_stem: str
    session_id: str
    coverage_type: str
    variant_label: str
    ticker: str
    count: int
    snapshot_count: int
    bid_ask_coverage_ratio: float
    median_spread_percent: float | None
    latest_turnover: float | None


@dataclass(frozen=True)
class AggregateRow:
    ticker: str
    session_count: int
    variants: tuple[str, ...]
    total_count: int
    baseline_count: int
    volume_ratio_disabled_count: int
    imbalance_disabled_count: int
    volume_and_imbalance_disabled_count: int
    coverage_label: str
    first_session: str
    notes: str


@dataclass(frozen=True)
class FilteredSignalTickerReport:
    aggregate_rows: list[AggregateRow]
    detail_rows: list[DetailRow]
    warnings: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a filtered signal ticker detail report. "
            "This filters exported signalTickerCounts only; it does not recompute signals."
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
        help="Exclude non-voting tickers such as .X0000.",
    )
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=[],
        help="Repeatable ticker substring exclusion pattern.",
    )
    parser.add_argument("--min-snapshots", type=int, help="Minimum snapshot count required.")
    parser.add_argument(
        "--min-bid-ask-coverage",
        type=float,
        help="Minimum bid/ask availability ratio required.",
    )
    parser.add_argument(
        "--max-median-spread",
        type=float,
        help="Maximum median spread percent allowed.",
    )
    parser.add_argument(
        "--min-latest-turnover",
        type=float,
        help="Minimum latest turnover required.",
    )
    parser.add_argument(
        "--min-max-volume",
        type=float,
        help="Minimum max volume required.",
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
                variant_path=session_dir / VARIANT_EXPORT_NAME,
            ),
        )
        for session_dir in session_dirs
    ]


def session_sort_key_for_path(path: Path) -> tuple[str, str]:
    return (path.stem, str(path))


def infer_session_path(variant_comparison: dict[str, object] | None) -> Path | None:
    if not isinstance(variant_comparison, dict):
        return None
    input_path = variant_comparison.get("inputPath")
    if isinstance(input_path, str) and input_path.strip():
        return Path(input_path)
    return None


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
    ordered = sorted(summary.quality.scan_mode_counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[0][0]


def resolve_session_id(
    summary: SessionSummary | None,
    variant_comparison: dict[str, object] | None,
) -> str:
    if summary is not None:
        return summary.session_id
    if isinstance(variant_comparison, dict):
        value = variant_comparison.get("sessionId")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "n/a"


def build_candidate_map(session: dict[str, object]) -> dict[str, UniverseCandidate]:
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
        ticker: summarize_universe_candidate(ticker, entries)
        for ticker, entries in grouped.items()
    }


def build_filtered_signal_ticker_report(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
) -> FilteredSignalTickerReport:
    resolved_filters = filters or UniverseCandidateFilters()
    warnings: list[str] = []
    detail_rows: list[DetailRow] = []
    aggregate_rollup: dict[str, dict[str, object]] = {}

    for record in discover_session_records(runtime_root, input_paths):
        if not record.runtime_artifacts.variant_path.is_file():
            warnings.append(f"{record.session_stem}: missing variant export")
            continue

        variant_comparison = load_variant_comparison(record.runtime_artifacts.variant_path)
        session_path = record.session_path or infer_session_path(variant_comparison)
        summary: SessionSummary | None = None
        candidate_map: dict[str, UniverseCandidate] | None = None

        if session_path is not None:
            try:
                session = load_session(session_path)
                summary = summarize_session(session)
                candidate_map = build_candidate_map(session)
            except SessionFormatError:
                warnings.append(f"{record.session_stem}: session JSON unreadable")
        else:
            warnings.append(f"{record.session_stem}: session JSON unreadable")

        session_context = SessionContext(
            session_stem=record.session_stem,
            session_id=resolve_session_id(summary, variant_comparison),
            session_path=session_path,
            coverage_type=classify_coverage_type(summary),
            summary=summary,
            candidates=candidate_map,
        )

        variant_rows = variant_comparison.get("variants")
        if not isinstance(variant_rows, list):
            continue

        for variant in variant_rows:
            if not isinstance(variant, dict):
                continue
            variant_name = variant.get("variantName")
            variant_label = EXPECTED_VARIANTS.get(variant_name)
            if variant_label is None:
                continue

            signal_ticker_counts = variant.get("signalTickerCounts")
            if not isinstance(signal_ticker_counts, list):
                continue

            listed_tickers = 0
            valid_signal_rows: list[tuple[str, int]] = []
            for signal_row in signal_ticker_counts:
                if not isinstance(signal_row, dict):
                    continue
                ticker = signal_row.get("ticker")
                count = signal_row.get("count")
                if not isinstance(ticker, str) or not isinstance(count, int):
                    continue
                listed_tickers += 1
                valid_signal_rows.append((ticker, count))

            unique_signal_tickers = variant.get("uniqueSignalTickers")
            if isinstance(unique_signal_tickers, int) and unique_signal_tickers > listed_tickers:
                warnings.append(
                    f"{record.session_stem} {variant_label}: partial export; counts below are lower bounds"
                )

            if candidate_map is None:
                continue

            for ticker, count in valid_signal_rows:
                candidate = candidate_map.get(ticker)
                if candidate is None:
                    continue
                if not candidate_matches_filters(candidate, resolved_filters):
                    continue

                detail_rows.append(
                    DetailRow(
                        session_stem=session_context.session_stem,
                        session_id=session_context.session_id,
                        coverage_type=session_context.coverage_type,
                        variant_label=variant_label,
                        ticker=ticker,
                        count=count,
                        snapshot_count=candidate.snapshot_count,
                        bid_ask_coverage_ratio=candidate.bid_ask_coverage_ratio,
                        median_spread_percent=candidate.median_spread_percent,
                        latest_turnover=candidate.latest_turnover,
                    )
                )

                rollup = aggregate_rollup.setdefault(
                    ticker,
                    {
                        "session_stems": set(),
                        "variant_labels": set(),
                        "coverage_types": set(),
                        "first_session": record.session_stem,
                        "counts": {label: 0 for label in VARIANT_LABEL_ORDER},
                    },
                )
                rollup["session_stems"].add(record.session_stem)
                rollup["variant_labels"].add(variant_label)
                rollup["coverage_types"].add(session_context.coverage_type)
                rollup["counts"][variant_label] += count
                if record.session_stem < rollup["first_session"]:
                    rollup["first_session"] = record.session_stem

    aggregate_rows = build_aggregate_rows_from_rollup(aggregate_rollup)
    ordered_detail_rows = sorted(
        detail_rows,
        key=lambda row: (
            row.session_stem,
            VARIANT_LABEL_ORDER.index(row.variant_label),
            row.ticker,
        ),
    )
    ordered_warnings = sorted(set(warnings))
    return FilteredSignalTickerReport(
        aggregate_rows=aggregate_rows,
        detail_rows=ordered_detail_rows,
        warnings=ordered_warnings,
    )


def build_aggregate_rows_from_rollup(
    aggregate_rollup: dict[str, dict[str, object]],
) -> list[AggregateRow]:
    rows: list[AggregateRow] = []
    for ticker, rollup in aggregate_rollup.items():
        counts = rollup["counts"]
        coverage_types = set(rollup["coverage_types"])
        if len(coverage_types) == 1:
            coverage_label = next(iter(coverage_types))
        else:
            coverage_label = "mixed"
        notes = (
            "partial-coverage-only"
            if coverage_types == {"partial-coverage"}
            else "-"
        )
        rows.append(
            AggregateRow(
                ticker=ticker,
                session_count=len(rollup["session_stems"]),
                variants=tuple(
                    label for label in VARIANT_LABEL_ORDER if label in rollup["variant_labels"]
                ),
                total_count=sum(int(counts[label]) for label in VARIANT_LABEL_ORDER),
                baseline_count=int(counts["base"]),
                volume_ratio_disabled_count=int(counts["vol-off"]),
                imbalance_disabled_count=int(counts["imb-off"]),
                volume_and_imbalance_disabled_count=int(counts["both-off"]),
                coverage_label=coverage_label,
                first_session=str(rollup["first_session"]),
                notes=notes,
            )
        )
    return sorted(rows, key=lambda row: (-row.total_count, row.ticker))


def fit_cell(value: str, width: int) -> str:
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    left_width = max((width - 3) // 2, 1)
    right_width = max(width - 3 - left_width, 1)
    return f"{value[:left_width]}...{value[-right_width:]}".ljust(width)


def format_number(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return format(value, ".2f").rstrip("0").rstrip(".")


def format_ratio(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def format_aggregate_section(rows: list[AggregateRow]) -> str:
    columns = [
        ("ticker", 14, lambda row: row.ticker),
        ("sessions", 8, lambda row: format_number(row.session_count)),
        ("variants", 21, lambda row: ",".join(row.variants)),
        ("total", 6, lambda row: format_number(row.total_count)),
        ("base", 6, lambda row: format_number(row.baseline_count)),
        ("vol-off", 7, lambda row: format_number(row.volume_ratio_disabled_count)),
        ("imb-off", 7, lambda row: format_number(row.imbalance_disabled_count)),
        ("both-off", 8, lambda row: format_number(row.volume_and_imbalance_disabled_count)),
        ("coverage", 18, lambda row: row.coverage_label),
        ("first-session", 24, lambda row: row.first_session),
        ("notes", 22, lambda row: row.notes),
    ]
    return format_table("Aggregate surviving tickers", rows, columns)


def format_detail_section(rows: list[DetailRow]) -> str:
    columns = [
        ("session", 24, lambda row: row.session_stem),
        ("coverage", 18, lambda row: row.coverage_type),
        ("variant", 8, lambda row: row.variant_label),
        ("ticker", 14, lambda row: row.ticker),
        ("count", 5, lambda row: format_number(row.count)),
        ("snapshots", 9, lambda row: format_number(row.snapshot_count)),
        ("bid/ask%", 9, lambda row: format_ratio(row.bid_ask_coverage_ratio)),
        ("medSpread%", 10, lambda row: format_percent(row.median_spread_percent)),
        ("latestTurn", 12, lambda row: format_number(row.latest_turnover)),
    ]
    return format_table("Per-session surviving ticker detail", rows, columns)


def format_table(title: str, rows: list[object], columns: list[tuple[str, int, object]]) -> str:
    header = " ".join(fit_cell(name, width) for name, width, _getter in columns)
    divider = " ".join("-" * width for _name, width, _getter in columns)
    body = [
        " ".join(fit_cell(getter(row), width) for _name, width, getter in columns)
        for row in rows
    ]
    if not body:
        body = ["No rows."]
    return "\n".join([title, header, divider, *body])


def format_warnings_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["Warnings"]
    lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def render_report(report: FilteredSignalTickerReport) -> str:
    sections = [
        "Sentinel-CSE filtered signal ticker detail report",
        "Research only: exported signalTickerCounts filtered from recorded session snapshots; no replay recomputation.",
        "",
        format_aggregate_section(report.aggregate_rows),
        "",
        format_detail_section(report.detail_rows),
    ]
    warnings_block = format_warnings_block(report.warnings)
    if warnings_block:
        sections.extend(["", warnings_block])
    return "\n".join(sections)


def run_filtered_signal_ticker_report(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
    output: TextIO | None = None,
) -> int:
    handle = output or io.StringIO()
    report = build_filtered_signal_ticker_report(runtime_root, input_paths, filters=filters)
    print(render_report(report), file=handle)
    if output is None:
        print(handle.getvalue(), end="")
    return 0


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
    return run_filtered_signal_ticker_report(
        runtime_root=Path(args.runtime_root),
        input_paths=flatten_inputs(args.input),
        filters=filters,
    )


if __name__ == "__main__":
    raise SystemExit(parse_args_and_run())
