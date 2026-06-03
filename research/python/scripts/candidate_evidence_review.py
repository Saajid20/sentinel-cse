from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from filtered_signal_ticker_report import (
    DEFAULT_RUNTIME_DIR,
    VARIANT_LABEL_ORDER,
    DetailRow as FilteredDetailRow,
    build_filtered_signal_ticker_report,
    flatten_inputs,
)
from universe_candidate_report import UniverseCandidateFilters

TIER_ORDER = {
    "Tier A": 0,
    "Tier B": 1,
    "Tier C": 2,
    "Tier D": 3,
}
REVIEW_STATUS_BY_TIER = {
    "Tier A": "MANUAL_REVIEW",
    "Tier B": "WATCHLIST_RESEARCH",
    "Tier C": "LOW_CONFIDENCE",
    "Tier D": "INSUFFICIENT_EVIDENCE",
}


@dataclass(frozen=True)
class CandidateReviewSummaryRow:
    ticker: str
    tier: str
    session_count: int
    strong_session_count: int
    partial_session_count: int
    variants: tuple[str, ...]
    total_count: int
    baseline_count: int
    diagnostic_count: int
    best_median_spread_percent: float | None
    best_bid_ask_coverage_ratio: float
    max_latest_turnover: float | None
    review_status: str
    notes: str


@dataclass(frozen=True)
class CandidateReviewDetailRow:
    ticker: str
    session_stem: str
    coverage_type: str
    variant_label: str
    count: int
    snapshot_count: int
    bid_ask_coverage_ratio: float
    median_spread_percent: float | None
    latest_turnover: float | None
    notes: str


@dataclass(frozen=True)
class CandidateEvidenceReviewReport:
    summary_rows: list[CandidateReviewSummaryRow]
    detail_rows: list[CandidateReviewDetailRow]
    warnings: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a candidate evidence review report from exported offline diagnostics. "
            "This is research-only and does not recompute signals."
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


def build_candidate_evidence_review(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
) -> CandidateEvidenceReviewReport:
    filtered_report = build_filtered_signal_ticker_report(
        runtime_root=runtime_root,
        input_paths=input_paths,
        filters=filters,
    )
    lower_bound_pairs = lower_bound_session_variants(filtered_report.warnings)
    detail_rows = build_detail_rows(filtered_report.detail_rows, lower_bound_pairs)
    summary_rows = build_summary_rows(detail_rows)
    return CandidateEvidenceReviewReport(
        summary_rows=summary_rows,
        detail_rows=detail_rows,
        warnings=filtered_report.warnings,
    )


def lower_bound_session_variants(warnings: list[str]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    marker = ": partial export; counts below are lower bounds"
    for warning in warnings:
        if marker not in warning:
            continue
        prefix = warning.split(":", 1)[0]
        if " " not in prefix:
            continue
        session_stem, variant_label = prefix.rsplit(" ", 1)
        pairs.add((session_stem, variant_label))
    return pairs


def build_detail_rows(
    filtered_rows: list[FilteredDetailRow],
    lower_bound_pairs: set[tuple[str, str]],
) -> list[CandidateReviewDetailRow]:
    rows = [
        CandidateReviewDetailRow(
            ticker=row.ticker,
            session_stem=row.session_stem,
            coverage_type=row.coverage_type,
            variant_label=row.variant_label,
            count=row.count,
            snapshot_count=row.snapshot_count,
            bid_ask_coverage_ratio=row.bid_ask_coverage_ratio,
            median_spread_percent=row.median_spread_percent,
            latest_turnover=row.latest_turnover,
            notes=(
                "lower-bound"
                if (row.session_stem, row.variant_label) in lower_bound_pairs
                else "-"
            ),
        )
        for row in filtered_rows
    ]
    return sorted(
        rows,
        key=lambda row: (
            row.ticker,
            row.session_stem,
            VARIANT_LABEL_ORDER.index(row.variant_label),
        ),
    )


def build_summary_rows(detail_rows: list[CandidateReviewDetailRow]) -> list[CandidateReviewSummaryRow]:
    grouped: dict[str, list[CandidateReviewDetailRow]] = {}
    for row in detail_rows:
        grouped.setdefault(row.ticker, []).append(row)

    summary_rows: list[CandidateReviewSummaryRow] = []
    for ticker, rows in grouped.items():
        session_stems = {row.session_stem for row in rows}
        strong_sessions = {
            row.session_stem for row in rows if row.coverage_type == "strong-full-grid"
        }
        partial_sessions = {
            row.session_stem for row in rows if row.coverage_type == "partial-coverage"
        }
        variants = tuple(
            label
            for label in VARIANT_LABEL_ORDER
            if any(row.variant_label == label for row in rows)
        )
        counts = {
            label: sum(row.count for row in rows if row.variant_label == label)
            for label in VARIANT_LABEL_ORDER
        }
        coverage_types = {row.coverage_type for row in rows}
        tier = classify_evidence_tier(
            session_count=len(session_stems),
            strong_session_count=len(strong_sessions),
            partial_session_count=len(partial_sessions),
            baseline_count=counts["base"],
        )
        notes = build_summary_notes(
            coverage_types=coverage_types,
            baseline_count=counts["base"],
            has_lower_bound=any(row.notes == "lower-bound" for row in rows),
        )
        median_spreads = [row.median_spread_percent for row in rows if row.median_spread_percent is not None]
        latest_turnovers = [row.latest_turnover for row in rows if row.latest_turnover is not None]
        summary_rows.append(
            CandidateReviewSummaryRow(
                ticker=ticker,
                tier=tier,
                session_count=len(session_stems),
                strong_session_count=len(strong_sessions),
                partial_session_count=len(partial_sessions),
                variants=variants,
                total_count=sum(counts.values()),
                baseline_count=counts["base"],
                diagnostic_count=counts["vol-off"] + counts["imb-off"] + counts["both-off"],
                best_median_spread_percent=min(median_spreads) if median_spreads else None,
                best_bid_ask_coverage_ratio=max(row.bid_ask_coverage_ratio for row in rows),
                max_latest_turnover=max(latest_turnovers) if latest_turnovers else None,
                review_status=REVIEW_STATUS_BY_TIER[tier],
                notes=notes,
            )
        )

    return sorted(
        summary_rows,
        key=lambda row: (
            TIER_ORDER[row.tier],
            -row.session_count,
            -row.strong_session_count,
            -row.total_count,
            row.ticker,
        ),
    )


def classify_evidence_tier(
    *,
    session_count: int,
    strong_session_count: int,
    partial_session_count: int,
    baseline_count: int,
) -> str:
    if session_count >= 2 and strong_session_count >= 1:
        return "Tier A"
    if partial_session_count == session_count and session_count >= 1:
        return "Tier C"
    if session_count == 1 and strong_session_count == 1 and baseline_count > 0:
        return "Tier B"
    return "Tier D"


def build_summary_notes(
    *,
    coverage_types: set[str],
    baseline_count: int,
    has_lower_bound: bool,
) -> str:
    notes: list[str] = []
    if coverage_types == {"partial-coverage"}:
        notes.append("partial-coverage-only")
    if baseline_count == 0:
        notes.append("diagnostic-only")
    if has_lower_bound:
        notes.append("lower-bound")
    return ", ".join(notes) if notes else "-"


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


def format_summary_section(rows: list[CandidateReviewSummaryRow]) -> str:
    columns = [
        ("ticker", 14, lambda row: row.ticker),
        ("tier", 6, lambda row: row.tier),
        ("sessions", 8, lambda row: format_number(row.session_count)),
        ("strong", 6, lambda row: format_number(row.strong_session_count)),
        ("partial", 7, lambda row: format_number(row.partial_session_count)),
        ("variants", 21, lambda row: ",".join(row.variants)),
        ("total", 6, lambda row: format_number(row.total_count)),
        ("base", 6, lambda row: format_number(row.baseline_count)),
        ("diagnostic", 10, lambda row: format_number(row.diagnostic_count)),
        ("bestMedSpr%", 11, lambda row: format_percent(row.best_median_spread_percent)),
        ("bestBidAsk%", 11, lambda row: format_ratio(row.best_bid_ask_coverage_ratio)),
        ("maxLatestTurn", 13, lambda row: format_number(row.max_latest_turnover)),
        ("review", 21, lambda row: row.review_status),
        ("notes", 31, lambda row: row.notes),
    ]
    return format_table("Candidate review summary", rows, columns)


def format_detail_section(rows: list[CandidateReviewDetailRow]) -> str:
    columns = [
        ("ticker", 14, lambda row: row.ticker),
        ("session", 24, lambda row: row.session_stem),
        ("coverage", 18, lambda row: row.coverage_type),
        ("variant", 8, lambda row: row.variant_label),
        ("count", 5, lambda row: format_number(row.count)),
        ("snapshots", 9, lambda row: format_number(row.snapshot_count)),
        ("bid/ask%", 9, lambda row: format_ratio(row.bid_ask_coverage_ratio)),
        ("medSpread%", 10, lambda row: format_percent(row.median_spread_percent)),
        ("latestTurn", 12, lambda row: format_number(row.latest_turnover)),
        ("notes", 12, lambda row: row.notes),
    ]
    return format_table("Candidate detail rows", rows, columns)


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


def format_safety_note() -> str:
    lines = [
        "Safety note",
        "- This report is research-only.",
        "- It is derived from exported offline diagnostics.",
        "- It is not financial advice.",
        "- It is not a buy/sell/hold recommendation.",
        "- It is not live execution guidance.",
        "- Human review is required.",
    ]
    return "\n".join(lines)


def render_report(report: CandidateEvidenceReviewReport) -> str:
    sections = [
        "Sentinel-CSE candidate evidence review",
        "Research/manual-review aid built from exported offline diagnostics; no replay recomputation.",
        "",
        format_summary_section(report.summary_rows),
        "",
        format_detail_section(report.detail_rows),
    ]
    warnings_block = format_warnings_block(report.warnings)
    if warnings_block:
        sections.extend(["", warnings_block])
    sections.extend(["", format_safety_note()])
    return "\n".join(sections)


def run_candidate_evidence_review(
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
    output: TextIO | None = None,
) -> int:
    handle = output or io.StringIO()
    report = build_candidate_evidence_review(runtime_root, input_paths, filters=filters)
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
    return run_candidate_evidence_review(
        runtime_root=Path(args.runtime_root),
        input_paths=flatten_inputs(args.input),
        filters=filters,
    )


if __name__ == "__main__":
    raise SystemExit(parse_args_and_run())
