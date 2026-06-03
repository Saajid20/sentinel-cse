from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from candidate_evidence_review import (
    REVIEW_STATUS_BY_TIER,
    build_candidate_evidence_review,
    lower_bound_session_variants,
)
from filtered_signal_ticker_report import (
    DEFAULT_RUNTIME_DIR,
    EXPECTED_VARIANTS,
    VARIANT_LABEL_ORDER,
    build_candidate_map,
    build_filtered_signal_ticker_report,
    discover_session_records,
    flatten_inputs,
)
from multi_session_aggregate_report import (
    REPLAY_EXPORT_NAME,
    resolve_coverage_summary,
    resolve_quality_classification,
    resolve_scan_mode_summary,
    resolve_total_snapshots,
    resolve_unique_tickers,
)
from strategy_blocker_report import load_replay_diagnostics
from summarize_session import SessionFormatError, SessionSummary, load_session, summarize_session
from universe_candidate_report import UniverseCandidate, UniverseCandidateFilters
from variant_comparison_report import load_variant_comparison


@dataclass(frozen=True)
class DossierHeader:
    ticker: str
    company_name: str | None
    evidence_tier: str
    review_status: str
    total_filtered_count: int
    sessions_seen: int
    strong_full_grid_sessions: int
    partial_coverage_sessions: int
    baseline_count: int
    volume_ratio_disabled_count: int
    imbalance_disabled_count: int
    volume_and_imbalance_disabled_count: int
    diagnostic_count: int
    variants_seen: tuple[str, ...]
    first_session: str | None
    last_session: str | None


@dataclass(frozen=True)
class SessionEvidenceRow:
    session_stem: str
    session_id: str
    coverage_type: str
    quality_classification: str
    total_snapshots: int | None
    unique_tickers: int | None
    scan_mode_summary: str
    peak_median_coverage: str
    ticker_snapshots: int | None
    bid_ask_coverage_ratio: float | None
    median_spread_percent: float | None
    latest_turnover: float | None
    company_name: str | None = None


@dataclass(frozen=True)
class FilteredSignalEvidenceRow:
    session_stem: str
    coverage_type: str
    variant_label: str
    count: int | None
    raw_variant_signal_count: int | None
    filtered_ticker_count: int | None
    notes: str


@dataclass(frozen=True)
class BlockerContextRow:
    session_stem: str
    snapshots: int | None
    history_pass: int | None
    strategy_ready: int | None
    spread_pass: int | None
    vwap_available: int | None
    price_above_vwap: int | None
    first_high_available: int | None
    momentum_pass: int | None
    volume_ratio_available: int | None
    volume_ratio_pass: int | None
    imbalance_available: int | None
    imbalance_pass: int | None
    signals: int | None
    top_blockers: tuple[str, ...]


@dataclass(frozen=True)
class CandidateEvidenceDossier:
    header: DossierHeader
    session_rows: list[SessionEvidenceRow]
    filtered_signal_rows: list[FilteredSignalEvidenceRow]
    blocker_rows: list[BlockerContextRow]
    warnings: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a single-ticker candidate evidence dossier from exported offline diagnostics. "
            "This is research-only and does not recompute signals."
        )
    )
    parser.add_argument("--ticker", required=True, help="Ticker to build a dossier for.")
    parser.add_argument(
        "--runtime-root",
        default=str(DEFAULT_RUNTIME_DIR),
        help="Runtime output root for multi-session validation exports.",
    )
    parser.add_argument(
        "--markdown-output",
        help=(
            "Optional Markdown export path, for example "
            ".runtime-pipeline/candidate-dossiers/PKME.N0000.md. "
            "Runtime outputs should not be committed."
        ),
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


def build_candidate_evidence_dossier(
    ticker: str,
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
) -> CandidateEvidenceDossier:
    normalized_ticker = ticker.strip().upper()
    resolved_filters = filters or UniverseCandidateFilters()
    review_report = build_candidate_evidence_review(
        runtime_root=runtime_root,
        input_paths=input_paths,
        filters=resolved_filters,
    )
    filtered_report = build_filtered_signal_ticker_report(
        runtime_root=runtime_root,
        input_paths=input_paths,
        filters=resolved_filters,
    )
    summary_row = next(
        (row for row in review_report.summary_rows if row.ticker.upper() == normalized_ticker),
        None,
    )
    filtered_rows = [
        row for row in filtered_report.detail_rows if row.ticker.upper() == normalized_ticker
    ]
    lower_bound_pairs = lower_bound_session_variants(review_report.warnings)
    unreadable_session_stems = parse_unreadable_session_stems(review_report.warnings)
    warnings = list(review_report.warnings)

    session_rows: list[SessionEvidenceRow] = []
    filtered_signal_rows: list[FilteredSignalEvidenceRow] = []
    blocker_rows: list[BlockerContextRow] = []
    company_name: str | None = None

    filtered_rows_by_session: dict[str, list[object]] = {}
    for row in filtered_rows:
        filtered_rows_by_session.setdefault(row.session_stem, []).append(row)

    records = discover_session_records(runtime_root, input_paths)
    for record in records:
        replay_path = runtime_root / record.session_stem / REPLAY_EXPORT_NAME
        variant_comparison = (
            load_variant_comparison(record.runtime_artifacts.variant_path)
            if record.runtime_artifacts.variant_path.is_file()
            else None
        )
        replay_diagnostics = (
            load_replay_diagnostics(replay_path)
            if replay_path.is_file()
            else None
        )
        session_path = record.session_path or infer_session_path_from_exports(
            replay_diagnostics,
            variant_comparison,
        )
        summary: SessionSummary | None = None
        candidate: UniverseCandidate | None = None
        if session_path is not None:
            try:
                session = load_session(session_path)
                summary = summarize_session(session)
                candidate = build_candidate_map(session).get(normalized_ticker)
            except SessionFormatError:
                pass

        runtime_variant_rows = extract_runtime_variant_rows(variant_comparison, normalized_ticker)
        per_session_filtered_rows = filtered_rows_by_session.get(record.session_stem, [])
        has_runtime_ticker_presence = any(row.target_ticker_count is not None for row in runtime_variant_rows.values())
        per_ticker_blocker = extract_ticker_replay_diagnostic(replay_diagnostics, normalized_ticker)

        if per_session_filtered_rows:
            session_rows.append(
                build_session_evidence_row(
                    session_stem=record.session_stem,
                    summary=summary,
                    replay_diagnostics=replay_diagnostics,
                    variant_comparison=variant_comparison,
                    coverage_type=per_session_filtered_rows[0].coverage_type,
                    candidate=candidate,
                )
            )
            if company_name is None and candidate is not None and candidate.company_name:
                company_name = candidate.company_name

            for row in sorted(
                per_session_filtered_rows,
                key=lambda item: VARIANT_LABEL_ORDER.index(item.variant_label),
            ):
                runtime_variant_row = runtime_variant_rows.get(row.variant_label)
                notes: list[str] = []
                if (record.session_stem, row.variant_label) in lower_bound_pairs:
                    notes.append("lower-bound")
                filtered_signal_rows.append(
                    FilteredSignalEvidenceRow(
                        session_stem=row.session_stem,
                        coverage_type=row.coverage_type,
                        variant_label=row.variant_label,
                        count=row.count,
                        raw_variant_signal_count=(
                            runtime_variant_row.raw_variant_signal_count
                            if runtime_variant_row is not None
                            else None
                        ),
                        filtered_ticker_count=row.count,
                        notes=", ".join(notes) if notes else "-",
                    )
                )

            blocker_rows.append(
                build_blocker_context_row(record.session_stem, per_ticker_blocker)
            )
            continue

        if record.session_stem in unreadable_session_stems and has_runtime_ticker_presence:
            session_rows.append(
                build_session_evidence_row(
                    session_stem=record.session_stem,
                    summary=summary,
                    replay_diagnostics=replay_diagnostics,
                    variant_comparison=variant_comparison,
                    coverage_type="unknown",
                    candidate=None,
                )
            )
            for variant_label in VARIANT_LABEL_ORDER:
                runtime_variant_row = runtime_variant_rows.get(variant_label)
                if runtime_variant_row is None or runtime_variant_row.target_ticker_count is None:
                    continue
                notes = ["session JSON unreadable", "filtered unavailable"]
                if (record.session_stem, variant_label) in lower_bound_pairs:
                    notes.append("lower-bound")
                filtered_signal_rows.append(
                    FilteredSignalEvidenceRow(
                        session_stem=record.session_stem,
                        coverage_type="unknown",
                        variant_label=variant_label,
                        count=runtime_variant_row.target_ticker_count,
                        raw_variant_signal_count=runtime_variant_row.raw_variant_signal_count,
                        filtered_ticker_count=None,
                        notes=", ".join(notes),
                    )
                )
            blocker_rows.append(
                build_blocker_context_row(record.session_stem, per_ticker_blocker)
            )

    if summary_row is None and not session_rows and not filtered_signal_rows and not blocker_rows:
        warnings.append("ticker did not survive active research filters")

    ordered_session_rows = sorted(session_rows, key=lambda row: row.session_stem)
    ordered_filtered_rows = sorted(
        filtered_signal_rows,
        key=lambda row: (
            row.session_stem,
            VARIANT_LABEL_ORDER.index(row.variant_label),
        ),
    )
    ordered_blocker_rows = sorted(blocker_rows, key=lambda row: row.session_stem)
    ordered_warnings = unique_sorted_warnings(warnings)

    return CandidateEvidenceDossier(
        header=build_dossier_header(normalized_ticker, company_name, summary_row, filtered_rows),
        session_rows=ordered_session_rows,
        filtered_signal_rows=ordered_filtered_rows,
        blocker_rows=ordered_blocker_rows,
        warnings=ordered_warnings,
    )


@dataclass(frozen=True)
class RuntimeVariantRow:
    raw_variant_signal_count: int | None
    target_ticker_count: int | None


def extract_runtime_variant_rows(
    variant_comparison: dict[str, object] | None,
    normalized_ticker: str,
) -> dict[str, RuntimeVariantRow]:
    rows: dict[str, RuntimeVariantRow] = {}
    if not isinstance(variant_comparison, dict):
        return rows
    variants = variant_comparison.get("variants")
    if not isinstance(variants, list):
        return rows
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_name = variant.get("variantName")
        variant_label = EXPECTED_VARIANTS.get(variant_name)
        if variant_label is None:
            continue
        raw_variant_signal_count = variant.get("signalsGenerated")
        if not isinstance(raw_variant_signal_count, int):
            raw_variant_signal_count = None
        target_ticker_count: int | None = None
        signal_ticker_counts = variant.get("signalTickerCounts")
        if isinstance(signal_ticker_counts, list):
            for signal_row in signal_ticker_counts:
                if not isinstance(signal_row, dict):
                    continue
                ticker = signal_row.get("ticker")
                count = signal_row.get("count")
                if (
                    isinstance(ticker, str)
                    and ticker.strip().upper() == normalized_ticker
                    and isinstance(count, int)
                ):
                    target_ticker_count = count
                    break
        rows[variant_label] = RuntimeVariantRow(
            raw_variant_signal_count=raw_variant_signal_count,
            target_ticker_count=target_ticker_count,
        )
    return rows


def build_dossier_header(
    normalized_ticker: str,
    company_name: str | None,
    summary_row: object | None,
    filtered_rows: list[object],
) -> DossierHeader:
    counts = {
        label: sum(
            int(row.count)
            for row in filtered_rows
            if row.variant_label == label and isinstance(row.count, int)
        )
        for label in VARIANT_LABEL_ORDER
    }
    ordered_sessions = sorted({row.session_stem for row in filtered_rows})
    if summary_row is None:
        return DossierHeader(
            ticker=normalized_ticker,
            company_name=company_name,
            evidence_tier="Tier D",
            review_status=REVIEW_STATUS_BY_TIER["Tier D"],
            total_filtered_count=sum(counts.values()),
            sessions_seen=len(ordered_sessions),
            strong_full_grid_sessions=0,
            partial_coverage_sessions=0,
            baseline_count=counts["base"],
            volume_ratio_disabled_count=counts["vol-off"],
            imbalance_disabled_count=counts["imb-off"],
            volume_and_imbalance_disabled_count=counts["both-off"],
            diagnostic_count=counts["vol-off"] + counts["imb-off"] + counts["both-off"],
            variants_seen=tuple(label for label in VARIANT_LABEL_ORDER if counts[label] > 0),
            first_session=ordered_sessions[0] if ordered_sessions else None,
            last_session=ordered_sessions[-1] if ordered_sessions else None,
        )

    return DossierHeader(
        ticker=summary_row.ticker,
        company_name=company_name,
        evidence_tier=summary_row.tier,
        review_status=summary_row.review_status,
        total_filtered_count=sum(counts.values()),
        sessions_seen=len(ordered_sessions),
        strong_full_grid_sessions=summary_row.strong_session_count,
        partial_coverage_sessions=summary_row.partial_session_count,
        baseline_count=counts["base"],
        volume_ratio_disabled_count=counts["vol-off"],
        imbalance_disabled_count=counts["imb-off"],
        volume_and_imbalance_disabled_count=counts["both-off"],
        diagnostic_count=counts["vol-off"] + counts["imb-off"] + counts["both-off"],
        variants_seen=tuple(label for label in VARIANT_LABEL_ORDER if counts[label] > 0),
        first_session=ordered_sessions[0] if ordered_sessions else None,
        last_session=ordered_sessions[-1] if ordered_sessions else None,
    )


def build_session_evidence_row(
    *,
    session_stem: str,
    summary: SessionSummary | None,
    replay_diagnostics: dict[str, object] | None,
    variant_comparison: dict[str, object] | None,
    coverage_type: str,
    candidate: UniverseCandidate | None,
) -> SessionEvidenceRow:
    return SessionEvidenceRow(
        session_stem=session_stem,
        session_id=resolve_session_id(summary, replay_diagnostics, variant_comparison),
        coverage_type=coverage_type,
        quality_classification=resolve_quality_classification(summary),
        total_snapshots=resolve_total_snapshots(summary, replay_diagnostics, variant_comparison),
        unique_tickers=resolve_unique_tickers(summary, replay_diagnostics, variant_comparison),
        scan_mode_summary=resolve_scan_mode_summary(summary),
        peak_median_coverage=resolve_coverage_summary(summary),
        ticker_snapshots=candidate.snapshot_count if candidate is not None else None,
        bid_ask_coverage_ratio=(
            candidate.bid_ask_coverage_ratio if candidate is not None else None
        ),
        median_spread_percent=(
            candidate.median_spread_percent if candidate is not None else None
        ),
        latest_turnover=(
            candidate.latest_turnover if candidate is not None else None
        ),
        company_name=candidate.company_name if candidate is not None else None,
    )


def build_blocker_context_row(
    session_stem: str,
    per_ticker_diagnostic: dict[str, object] | None,
) -> BlockerContextRow:
    if not isinstance(per_ticker_diagnostic, dict):
        return BlockerContextRow(
            session_stem=session_stem,
            snapshots=None,
            history_pass=None,
            strategy_ready=None,
            spread_pass=None,
            vwap_available=None,
            price_above_vwap=None,
            first_high_available=None,
            momentum_pass=None,
            volume_ratio_available=None,
            volume_ratio_pass=None,
            imbalance_available=None,
            imbalance_pass=None,
            signals=None,
            top_blockers=(),
        )

    return BlockerContextRow(
        session_stem=session_stem,
        snapshots=optional_int(per_ticker_diagnostic.get("snapshots")),
        history_pass=optional_int(per_ticker_diagnostic.get("historyPass")),
        strategy_ready=optional_int(per_ticker_diagnostic.get("strategyReady")),
        spread_pass=optional_int(per_ticker_diagnostic.get("spreadPass")),
        vwap_available=optional_int(per_ticker_diagnostic.get("vwapAvailable")),
        price_above_vwap=optional_int(per_ticker_diagnostic.get("priceAboveVwap")),
        first_high_available=optional_int(per_ticker_diagnostic.get("firstHighAvailable")),
        momentum_pass=optional_int(per_ticker_diagnostic.get("momentumPass")),
        volume_ratio_available=optional_int(per_ticker_diagnostic.get("volumeRatioAvailable")),
        volume_ratio_pass=optional_int(per_ticker_diagnostic.get("volumeRatioPass")),
        imbalance_available=optional_int(per_ticker_diagnostic.get("imbalanceAvailable")),
        imbalance_pass=optional_int(per_ticker_diagnostic.get("imbalancePass")),
        signals=optional_int(per_ticker_diagnostic.get("signals")),
        top_blockers=parse_string_tuple(per_ticker_diagnostic.get("topBlockers")),
    )


def parse_unreadable_session_stems(warnings: list[str]) -> set[str]:
    marker = ": session JSON unreadable"
    return {
        warning.split(":", 1)[0]
        for warning in warnings
        if warning.endswith(marker)
    }


def infer_session_path_from_exports(
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


def extract_ticker_replay_diagnostic(
    replay_diagnostics: dict[str, object] | None,
    normalized_ticker: str,
) -> dict[str, object] | None:
    if not isinstance(replay_diagnostics, dict):
        return None
    rows = replay_diagnostics.get("perTickerConditionDiagnostics")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if isinstance(ticker, str) and ticker.strip().upper() == normalized_ticker:
            return row
    return None


def optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    )


def unique_sorted_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            ordered.append(warning)
    return ordered


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


def format_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def format_tuple(value: tuple[str, ...]) -> str:
    return ",".join(value) if value else "n/a"


def format_top_blockers(value: tuple[str, ...]) -> str:
    return ", ".join(value) if value else "n/a"


def format_header_section(header: DossierHeader) -> str:
    lines = [
        "Dossier header",
        f"ticker: {header.ticker}",
        f"company name: {header.company_name or 'n/a'}",
        f"evidence tier: {header.evidence_tier}",
        f"review status: {header.review_status}",
        f"total filtered count: {format_number(header.total_filtered_count)}",
        f"sessions seen: {format_number(header.sessions_seen)}",
        f"strong-full-grid sessions: {format_number(header.strong_full_grid_sessions)}",
        f"partial-coverage sessions: {format_number(header.partial_coverage_sessions)}",
        f"baseline count: {format_number(header.baseline_count)}",
        f"volume-off count: {format_number(header.volume_ratio_disabled_count)}",
        f"imbalance-off count: {format_number(header.imbalance_disabled_count)}",
        f"both-off count: {format_number(header.volume_and_imbalance_disabled_count)}",
        f"diagnostic count: {format_number(header.diagnostic_count)}",
        f"variants seen: {format_tuple(header.variants_seen)}",
        f"first session: {header.first_session or 'n/a'}",
        f"last session: {header.last_session or 'n/a'}",
    ]
    return "\n".join(lines)


def format_session_evidence_section(rows: list[SessionEvidenceRow]) -> str:
    columns = [
        ("session", 24, lambda row: row.session_stem),
        ("sessionId", 24, lambda row: row.session_id),
        ("coverage", 18, lambda row: row.coverage_type),
        ("quality", 7, lambda row: row.quality_classification),
        ("snaps", 7, lambda row: format_number(row.total_snapshots)),
        ("tickers", 7, lambda row: format_number(row.unique_tickers)),
        ("scan", 30, lambda row: row.scan_mode_summary),
        ("peak/med", 12, lambda row: row.peak_median_coverage),
        ("t-snap", 7, lambda row: format_number(row.ticker_snapshots)),
        ("bid/ask", 9, lambda row: format_ratio(row.bid_ask_coverage_ratio)),
        ("medSpr", 8, lambda row: format_percent(row.median_spread_percent)),
        ("latestTurn", 12, lambda row: format_number(row.latest_turnover)),
    ]
    return format_table("Session evidence table", rows, columns)


def format_filtered_signal_section(rows: list[FilteredSignalEvidenceRow]) -> str:
    columns = [
        ("session", 24, lambda row: row.session_stem),
        ("coverage", 18, lambda row: row.coverage_type),
        ("variant", 8, lambda row: row.variant_label),
        ("count", 5, lambda row: format_number(row.count)),
        ("raw-var", 7, lambda row: format_number(row.raw_variant_signal_count)),
        ("f-count", 7, lambda row: format_number(row.filtered_ticker_count)),
        ("notes", 36, lambda row: row.notes),
    ]
    return format_table("Filtered signal evidence", rows, columns)


def format_variant_interpretation_section(header: DossierHeader) -> str:
    lines = [
        "Variant interpretation",
        f"- baseline evidence count: {format_number(header.baseline_count)}",
        f"- volume-off diagnostic evidence count: {format_number(header.volume_ratio_disabled_count)}",
        f"- imbalance-off diagnostic evidence count: {format_number(header.imbalance_disabled_count)}",
        f"- both-off diagnostic evidence count: {format_number(header.volume_and_imbalance_disabled_count)}",
        f"- diagnostic-only warning: {'yes' if header.baseline_count == 0 else 'no'}",
        (
            f"- evidence appears in strong-full-grid sessions: "
            f"{'yes' if header.strong_full_grid_sessions > 0 else 'no'}"
        ),
    ]
    return "\n".join(lines)


def format_blocker_context_section(rows: list[BlockerContextRow]) -> str:
    columns = [
        ("session", 24, lambda row: row.session_stem),
        ("snap", 5, lambda row: format_number(row.snapshots)),
        ("hist", 5, lambda row: format_number(row.history_pass)),
        ("ready", 5, lambda row: format_number(row.strategy_ready)),
        ("spread", 6, lambda row: format_number(row.spread_pass)),
        ("vwap", 5, lambda row: format_number(row.vwap_available)),
        ("p>vwap", 6, lambda row: format_number(row.price_above_vwap)),
        ("firstHi", 7, lambda row: format_number(row.first_high_available)),
        ("moment", 6, lambda row: format_number(row.momentum_pass)),
        ("volAvail", 8, lambda row: format_number(row.volume_ratio_available)),
        ("volPass", 7, lambda row: format_number(row.volume_ratio_pass)),
        ("imbAvail", 8, lambda row: format_number(row.imbalance_available)),
        ("imbPass", 7, lambda row: format_number(row.imbalance_pass)),
        ("signals", 7, lambda row: format_number(row.signals)),
        ("topBlockers", 34, lambda row: format_top_blockers(row.top_blockers)),
    ]
    return format_table("Blocker context", rows, columns)


def format_placeholders_section() -> str:
    lines = [
        "R10/R11 readiness placeholders",
        "- R10 context/risk review: pending",
        "- R11 financial statement review: pending",
        "- CSE disclosure review: pending",
        "- manual human notes: pending",
    ]
    return "\n".join(lines)


def format_safety_note() -> str:
    lines = [
        "Safety note",
        "- This dossier is research-only.",
        "- It is derived from exported offline diagnostics.",
        "- It is not financial advice.",
        "- It is not a buy/sell/hold recommendation.",
        "- It is not live execution guidance.",
        "- Human review is required.",
    ]
    return "\n".join(lines)


def format_warnings_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["Warnings"]
    lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def markdown_escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def markdown_table(
    columns: list[tuple[str, object]],
    rows: list[object],
) -> str:
    header = "| " + " | ".join(name for name, _getter in columns) + " |"
    divider = "| " + " | ".join("---" for _name, _getter in columns) + " |"
    body = [
        "| "
        + " | ".join(markdown_escape_cell(getter(row)) for _name, getter in columns)
        + " |"
        for row in rows
    ]
    if not body:
        body = ["No rows."]
    return "\n".join([header, divider, *body])


def render_markdown_report(
    report: CandidateEvidenceDossier,
    *,
    runtime_root: Path,
    input_paths: list[Path],
) -> str:
    session_columns = [
        ("session", lambda row: row.session_stem),
        ("sessionId", lambda row: row.session_id),
        ("coverage", lambda row: row.coverage_type),
        ("quality", lambda row: row.quality_classification),
        ("total snapshots", lambda row: format_number(row.total_snapshots)),
        ("unique tickers", lambda row: format_number(row.unique_tickers)),
        ("scan summary", lambda row: row.scan_mode_summary),
        ("peak/median coverage", lambda row: row.peak_median_coverage),
        ("ticker snapshots", lambda row: format_number(row.ticker_snapshots)),
        ("bid/ask coverage", lambda row: format_ratio(row.bid_ask_coverage_ratio)),
        ("median spread", lambda row: format_percent(row.median_spread_percent)),
        ("latest turnover", lambda row: format_number(row.latest_turnover)),
    ]
    filtered_signal_columns = [
        ("session", lambda row: row.session_stem),
        ("coverage", lambda row: row.coverage_type),
        ("variant", lambda row: row.variant_label),
        ("count", lambda row: format_number(row.count)),
        ("raw variant signal count", lambda row: format_number(row.raw_variant_signal_count)),
        ("filtered count for this ticker", lambda row: format_number(row.filtered_ticker_count)),
        ("notes", lambda row: row.notes),
    ]
    blocker_columns = [
        ("session", lambda row: row.session_stem),
        ("snapshots", lambda row: format_number(row.snapshots)),
        ("historyPass", lambda row: format_number(row.history_pass)),
        ("strategyReady", lambda row: format_number(row.strategy_ready)),
        ("spreadPass", lambda row: format_number(row.spread_pass)),
        ("vwapAvailable", lambda row: format_number(row.vwap_available)),
        ("priceAboveVwap", lambda row: format_number(row.price_above_vwap)),
        ("firstHighAvailable", lambda row: format_number(row.first_high_available)),
        ("momentumPass", lambda row: format_number(row.momentum_pass)),
        ("volumeRatioAvailable", lambda row: format_number(row.volume_ratio_available)),
        ("volumeRatioPass", lambda row: format_number(row.volume_ratio_pass)),
        ("imbalanceAvailable", lambda row: format_number(row.imbalance_available)),
        ("imbalancePass", lambda row: format_number(row.imbalance_pass)),
        ("signals", lambda row: format_number(row.signals)),
        ("topBlockers", lambda row: format_top_blockers(row.top_blockers)),
    ]
    input_note = ", ".join(str(path) for path in input_paths) if input_paths else "runtime discovery only"
    lines = [
        f"# Candidate Evidence Dossier - {report.header.ticker}",
        "",
        "## Safety notice",
        "- This dossier is research-only.",
        "- It is derived from exported offline diagnostics.",
        "- It is based on exported offline diagnostics and raw session metrics where available.",
        "- It is not financial advice.",
        "- It is not a buy/sell/hold recommendation.",
        "- It is not live execution guidance.",
        "- Human review is required.",
        "",
        "## Dossier header",
        f"- ticker: {report.header.ticker}",
        f"- company name: {report.header.company_name or 'n/a'}",
        f"- evidence tier: {report.header.evidence_tier}",
        f"- review status: {report.header.review_status}",
        f"- total filtered count: {format_number(report.header.total_filtered_count)}",
        f"- sessions seen: {format_number(report.header.sessions_seen)}",
        f"- strong-full-grid sessions: {format_number(report.header.strong_full_grid_sessions)}",
        f"- partial-coverage sessions: {format_number(report.header.partial_coverage_sessions)}",
        f"- baseline count: {format_number(report.header.baseline_count)}",
        f"- volume-off count: {format_number(report.header.volume_ratio_disabled_count)}",
        f"- imbalance-off count: {format_number(report.header.imbalance_disabled_count)}",
        f"- both-off count: {format_number(report.header.volume_and_imbalance_disabled_count)}",
        f"- diagnostic count: {format_number(report.header.diagnostic_count)}",
        f"- variants seen: {format_tuple(report.header.variants_seen)}",
        f"- first session: {report.header.first_session or 'n/a'}",
        f"- last session: {report.header.last_session or 'n/a'}",
        "",
        "## Session evidence table",
        markdown_table(session_columns, report.session_rows),
        "",
        "## Filtered signal evidence table",
        markdown_table(filtered_signal_columns, report.filtered_signal_rows),
        "",
        "## Variant interpretation",
        f"- baseline evidence count: {format_number(report.header.baseline_count)}",
        f"- volume-off diagnostic evidence count: {format_number(report.header.volume_ratio_disabled_count)}",
        f"- imbalance-off diagnostic evidence count: {format_number(report.header.imbalance_disabled_count)}",
        f"- both-off diagnostic evidence count: {format_number(report.header.volume_and_imbalance_disabled_count)}",
        f"- diagnostic-only warning: {'yes' if report.header.baseline_count == 0 else 'no'}",
        (
            "- evidence appears in strong-full-grid sessions: "
            f"{'yes' if report.header.strong_full_grid_sessions > 0 else 'no'}"
        ),
        "",
        "## Blocker context table",
        markdown_table(blocker_columns, report.blocker_rows),
        "",
        "## R10/R11 readiness placeholders",
        "- R10 context/risk review: pending",
        "- R11 financial statement review: pending",
        "- CSE disclosure review: pending",
        "- manual human notes: pending",
        "",
        "## Warnings / limitations",
    ]
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Generated-from/runtime source notes",
            f"- runtime root: {runtime_root}",
            f"- input selection: {input_note}",
            "- Runtime artifacts should not be committed.",
            "- This dossier is based on exported offline diagnostics and raw session metrics where available.",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def render_report(report: CandidateEvidenceDossier) -> str:
    sections = [
        "Sentinel-CSE candidate evidence dossier",
        "Research/manual-review aid built from exported offline diagnostics; no replay recomputation.",
        "",
        format_header_section(report.header),
        "",
        format_session_evidence_section(report.session_rows),
        "",
        format_filtered_signal_section(report.filtered_signal_rows),
        "",
        format_variant_interpretation_section(report.header),
        "",
        format_blocker_context_section(report.blocker_rows),
    ]
    warnings_block = format_warnings_block(report.warnings)
    if warnings_block:
        sections.extend(["", warnings_block])
    sections.extend(
        [
            "",
            format_placeholders_section(),
            "",
            format_safety_note(),
        ]
    )
    return "\n".join(sections)


def run_candidate_evidence_dossier(
    ticker: str,
    runtime_root: Path,
    input_paths: list[Path],
    filters: UniverseCandidateFilters | None = None,
    markdown_output: Path | None = None,
    output: TextIO | None = None,
) -> int:
    handle = output or io.StringIO()
    report = build_candidate_evidence_dossier(
        ticker=ticker,
        runtime_root=runtime_root,
        input_paths=input_paths,
        filters=filters,
    )
    if markdown_output is not None:
        markdown_content = render_markdown_report(
            report,
            runtime_root=runtime_root,
            input_paths=input_paths,
        )
        write_markdown_report(markdown_output, markdown_content)
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
    return run_candidate_evidence_dossier(
        ticker=args.ticker,
        runtime_root=Path(args.runtime_root),
        input_paths=flatten_inputs(args.input),
        filters=filters,
        markdown_output=Path(args.markdown_output) if args.markdown_output else None,
    )


if __name__ == "__main__":
    raise SystemExit(parse_args_and_run())
