from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.extraction import (  # noqa: E402
    ParsedFinancialRow,
    PypdfBaselineExtractor,
    R11ExtractionError,
    StatementPageMatch,
    classify_statement_page,
    locate_statement_pages,
    parse_financial_rows_from_table,
)
from sentinel_research.agents.r11.analysis.metric_aggregator import (  # noqa: E402
    aggregate_metric_results,
    has_metric_conflicts,
)
from sentinel_research.agents.r11.analysis.metric_builder import (  # noqa: E402
    R11MetricBuildError,
    build_growth_metric_for_item,
)
from sentinel_research.agents.r11.analysis.scorecard_builder import (  # noqa: E402
    R11ScorecardBuildError,
    build_fundamental_scorecard_from_aggregated_metrics,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    ExtractedFinancialTable,
    FinancialStatementType,
)
from sentinel_research.agents.r11.tables import (  # noqa: E402
    MappedLineItemValues,
    map_comb_six_column_items,
    normalize_parsed_financial_rows,
)

_GROUP_INCOME_STATEMENT_MARKERS = (
    "non-controlling interest",
    "non controlling interest",
    "equity holders of the parent",
    "equity holders of the bank",
    "attributable to equity holders",
)
_INCOME_STATEMENT_METRIC_ITEMS = {
    "basic_eps",
    "diluted_eps",
    "gross_income",
    "impairment_charges_and_other_losses",
    "interest_income",
    "net_interest_income",
    "operating_expenses",
    "profit_for_the_period",
    "total_operating_income",
}
_BALANCE_SHEET_METRIC_ITEMS = {
    "customer_deposits",
    "net_asset_value_per_share",
    "total_assets",
    "total_equity",
    "total_liabilities",
}


def _validate_positive_int(value: int | str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be > 0")
    return parsed


def _validate_non_negative_int(value: int | str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed < 0:
        raise ValueError(f"{name} must be >= 0")
    return parsed


def _positive_int(name: str):
    def _parser(value: str) -> int:
        try:
            return _validate_positive_int(value, name)
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    return _parser


def _non_negative_int(name: str):
    def _parser(value: str) -> int:
        try:
            return _validate_non_negative_int(value, name)
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    return _parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual inspection script for the R11 pypdf baseline table/text extractor."
    )
    parser.add_argument("--pdf", required=True, help="Path to a local PDF file.")
    parser.add_argument(
        "--start-page",
        type=_positive_int("start_page"),
        help="Only include extracted tables from this 1-based page number onward.",
    )
    parser.add_argument(
        "--end-page",
        type=_positive_int("end_page"),
        help="Only include extracted tables up to this 1-based page number.",
    )
    parser.add_argument(
        "--search",
        action="append",
        help="Case-insensitive text search term. May be passed multiple times.",
    )
    parser.add_argument(
        "--show-matches",
        action="store_true",
        help="Print matching lines and surrounding context when --search is used.",
    )
    parser.add_argument(
        "--context-lines",
        type=_non_negative_int("context_lines"),
        default=1,
        help="Number of lines before and after each match to print.",
    )
    parser.add_argument(
        "--limit-pages",
        type=_positive_int("limit_pages"),
        help="Only print the first N extracted page tables.",
    )
    parser.add_argument(
        "--max-lines-per-page",
        type=_positive_int("max_lines_per_page"),
        default=25,
        help="Maximum extracted lines to print per page table.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output path for extracted tables as UTF-8 JSON.",
    )
    parser.add_argument(
        "--output-analysis-json",
        help="Optional output path for deterministic R11 analysis artifacts as UTF-8 JSON.",
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print full JSON for each shown ExtractedFinancialTable.",
    )
    parser.add_argument(
        "--show-parsed-rows",
        action="store_true",
        help="Print parsed financial rows for each shown page/table.",
    )
    parser.add_argument(
        "--max-parsed-rows",
        type=_positive_int("max_parsed_rows"),
        default=30,
        help="Maximum parsed financial rows to print per shown page/table.",
    )
    parser.add_argument(
        "--show-parsed-json",
        action="store_true",
        help="Print full JSON for each displayed parsed financial row.",
    )
    parser.add_argument(
        "--show-normalized-rows",
        action="store_true",
        help="Print normalized financial line items for each shown page/table.",
    )
    parser.add_argument(
        "--max-normalized-rows",
        type=_positive_int("max_normalized_rows"),
        default=30,
        help="Maximum normalized financial rows to print per shown page/table.",
    )
    parser.add_argument(
        "--show-normalized-json",
        action="store_true",
        help="Print full JSON for each displayed normalized financial line item.",
    )
    parser.add_argument(
        "--show-mapped-values",
        action="store_true",
        help="Print mapped semantic values for each shown page/table.",
    )
    parser.add_argument(
        "--max-mapped-values",
        type=_positive_int("max_mapped_values"),
        default=30,
        help="Maximum mapped semantic value rows to print per shown page/table.",
    )
    parser.add_argument(
        "--show-mapped-json",
        action="store_true",
        help="Print full JSON for each displayed mapped semantic value item.",
    )
    parser.add_argument(
        "--show-verified-metrics",
        action="store_true",
        help="Print verified financial metrics for each shown page/table.",
    )
    parser.add_argument(
        "--metric-entity",
        choices=("group", "bank"),
        default="group",
        help="Entity prefix to use for verified metrics.",
    )
    parser.add_argument(
        "--max-verified-metrics",
        type=_positive_int("max_verified_metrics"),
        default=30,
        help="Maximum verified financial metrics to print per shown page/table.",
    )
    parser.add_argument(
        "--show-verified-json",
        action="store_true",
        help="Print full JSON for each displayed verified financial metric result.",
    )
    parser.add_argument(
        "--show-aggregated-metrics",
        action="store_true",
        help="Print aggregated verified metrics across all shown page/tables.",
    )
    parser.add_argument(
        "--max-aggregated-metrics",
        type=_positive_int("max_aggregated_metrics"),
        default=30,
        help="Maximum aggregated verified metrics to print.",
    )
    parser.add_argument(
        "--show-aggregated-json",
        action="store_true",
        help="Print full JSON for each displayed aggregated verified metric result.",
    )
    parser.add_argument(
        "--show-scorecard",
        action="store_true",
        help="Print the deterministic FundamentalScorecard built from aggregated verified metrics.",
    )
    parser.add_argument(
        "--show-scorecard-json",
        action="store_true",
        help="Print full JSON for the displayed deterministic scorecard build result.",
    )
    parser.add_argument(
        "--hide-statement-classification",
        action="store_true",
        help="Hide detected statement classification output.",
    )
    parser.add_argument(
        "--min-non-empty-lines",
        type=_positive_int("min_non_empty_lines"),
        default=2,
        help="Minimum non-empty lines required for a page to be included.",
    )
    return parser


def _validate_page_range(start_page: int | None, end_page: int | None) -> None:
    if start_page is not None:
        _validate_positive_int(start_page, "start_page")
    if end_page is not None:
        _validate_positive_int(end_page, "end_page")
    if start_page is not None and end_page is not None and start_page > end_page:
        raise ValueError("start_page must be <= end_page")


def _normalize_search_terms(search_terms: list[str] | None) -> list[str]:
    if not search_terms:
        return []

    normalized: list[str] = []
    for term in search_terms:
        stripped = term.strip().lower()
        if stripped:
            normalized.append(stripped)
    return normalized


def _matching_line_numbers(
    table: ExtractedFinancialTable,
    search_terms: list[str] | None,
) -> list[int]:
    normalized_terms = _normalize_search_terms(search_terms)
    if not normalized_terms:
        return []

    matches: list[int] = []
    for row in table.rows:
        text = str(row.get("text", "")).lower()
        if any(term in text for term in normalized_terms):
            matches.append(int(row["line_number"]))
    return matches


def _table_matches_search(
    table: ExtractedFinancialTable,
    search_terms: list[str] | None,
) -> bool:
    return bool(_matching_line_numbers(table, search_terms)) or not _normalize_search_terms(
        search_terms
    )


def _filter_tables(
    tables: list[ExtractedFinancialTable],
    *,
    start_page: int | None = None,
    end_page: int | None = None,
    search_terms: list[str] | None = None,
) -> list[ExtractedFinancialTable]:
    _validate_page_range(start_page, end_page)
    normalized_terms = _normalize_search_terms(search_terms)

    filtered: list[ExtractedFinancialTable] = []
    for table in tables:
        page_number = table.page_number
        if start_page is not None and page_number is not None and page_number < start_page:
            continue
        if end_page is not None and page_number is not None and page_number > end_page:
            continue
        if normalized_terms and not _table_matches_search(table, normalized_terms):
            continue
        filtered.append(table)
    return filtered


def _line_context(
    rows: list[dict[str, object]],
    line_number: int,
    context_lines: int,
) -> list[dict[str, object]]:
    normalized_context = _validate_non_negative_int(context_lines, "context_lines")
    if line_number <= 0:
        raise ValueError("line_number must be > 0")

    start_index = max(0, line_number - 1 - normalized_context)
    end_index = min(len(rows), line_number + normalized_context)
    return rows[start_index:end_index]


def _iter_shown_tables(
    tables: list[ExtractedFinancialTable],
    limit_pages: int | None,
) -> list[ExtractedFinancialTable]:
    if limit_pages is None:
        return tables
    return tables[:limit_pages]


def _active_filters(
    *,
    search_terms: list[str] | None,
    start_page: int | None,
    end_page: int | None,
) -> list[str]:
    active_filters: list[str] = []
    if start_page is not None:
        active_filters.append(f"start_page>={start_page}")
    if end_page is not None:
        active_filters.append(f"end_page<={end_page}")
    normalized_terms = _normalize_search_terms(search_terms)
    if normalized_terms:
        active_filters.append(f"search={normalized_terms}")
    return active_filters


def _print_summary(
    *,
    pdf_path: Path,
    tables: list[ExtractedFinancialTable],
    filtered_tables: list[ExtractedFinancialTable],
    shown_tables: list[ExtractedFinancialTable],
    statement_matches: list[StatementPageMatch],
    search_terms: list[str] | None,
    start_page: int | None,
    end_page: int | None,
    hide_statement_classification: bool,
    total_verified_metrics: int | None = None,
) -> None:
    pages = [table.page_number for table in tables if table.page_number is not None]
    filtered_pages = [
        table.page_number for table in filtered_tables if table.page_number is not None
    ]
    shown_pages = [table.page_number for table in shown_tables if table.page_number is not None]
    extraction_method = tables[0].extraction_method if tables else "unknown"
    active_filters = _active_filters(
        search_terms=search_terms,
        start_page=start_page,
        end_page=end_page,
    )

    print("R11 pypdf Baseline Inspection")
    print(f"PDF path: {pdf_path.resolve()}")
    print(f"total extracted page count: {len(tables)}")
    print(f"filtered page count: {len(filtered_tables)}")
    print(f"extraction method: {extraction_method}")
    print(f"active filters: {active_filters or ['none']}")
    print(f"pages extracted: {pages}")
    print(f"pages matched: {filtered_pages}")
    print(f"pages shown/saved: {shown_pages}")
    if total_verified_metrics is not None:
        print(f"total verified metric count: {total_verified_metrics}")
    if not hide_statement_classification:
        print("statement classifications:")
        for match in statement_matches:
            print(
                f"  page {match.page_number}: "
                f"{match.statement_type.value} {match.confidence.value}"
            )


def _print_table_preview(
    *,
    table: ExtractedFinancialTable,
    statement_match: StatementPageMatch | None,
    max_lines_per_page: int,
    show_json: bool,
    search_terms: list[str] | None,
    show_matches: bool,
    context_lines: int,
    hide_statement_classification: bool,
    show_parsed_rows: bool,
    max_parsed_rows: int,
    show_parsed_json: bool,
    show_normalized_rows: bool,
    max_normalized_rows: int,
    show_normalized_json: bool,
    show_mapped_values: bool,
    max_mapped_values: int,
    show_mapped_json: bool,
    show_verified_metrics: bool,
    metric_entity: str,
    max_verified_metrics: int,
    show_verified_json: bool,
) -> int:
    print()
    print(f"table_id: {table.table_id}")
    print(f"page_number: {table.page_number}")
    print(f"extraction_confidence: {table.extraction_confidence.value}")
    if not hide_statement_classification and statement_match is not None:
        print(f"statement_type: {statement_match.statement_type.value}")
        print(f"statement_confidence: {statement_match.confidence.value}")
        print(f"matched_markers: {statement_match.matched_markers}")
    print(f"line count: {len(table.rows)}")
    print(f"first {min(len(table.rows), max_lines_per_page)} lines:")

    for row in table.rows[:max_lines_per_page]:
        print(f"  {row['line_number']}: {row['text']}")

    if show_matches and _normalize_search_terms(search_terms):
        matching_line_numbers = _matching_line_numbers(table, search_terms)
        print("matching lines:")
        for line_number in matching_line_numbers:
            for row in _line_context(table.rows, line_number, context_lines):
                prefix = ">" if int(row["line_number"]) == line_number else " "
                print(f" {prefix} {row['line_number']}: {row['text']}")
            print(" ---")

    parsed_rows: list[ParsedFinancialRow] = []
    if (
        show_parsed_rows
        or show_normalized_rows
        or show_mapped_values
        or show_verified_metrics
    ):
        parsed_rows = parse_financial_rows_from_table(
            table,
            statement_type=statement_match.statement_type if statement_match is not None else None,
        )

    if show_parsed_rows:
        print(f"parsed financial rows: {len(parsed_rows)}")
        for parsed_row in parsed_rows[:max_parsed_rows]:
            _print_parsed_row(parsed_row, show_parsed_json=show_parsed_json)

    normalized_rows = []
    if show_normalized_rows or show_mapped_values or show_verified_metrics:
        normalized_rows = normalize_parsed_financial_rows(parsed_rows)

    if show_normalized_rows:
        print(f"normalized financial rows: {len(normalized_rows)}")
        for normalized_row in normalized_rows[:max_normalized_rows]:
            _print_normalized_row(
                normalized_row,
                show_normalized_json=show_normalized_json,
            )

    mapped_items = []
    if show_mapped_values or show_verified_metrics:
        mapped_items = map_comb_six_column_items(normalized_rows)

    if show_mapped_values:
        print(f"mapped semantic values: {len(mapped_items)}")
        for mapped_item in mapped_items[:max_mapped_values]:
            _print_mapped_item(mapped_item, show_mapped_json=show_mapped_json)

    verified_metric_count = 0
    if show_verified_metrics:
        verified_results, metric_build_warnings = _build_verified_metric_results_for_mapped_items(
            mapped_items,
            metric_entity=metric_entity,
        )
        verified_metric_count = len(verified_results)
        print(f"verified financial metrics: {verified_metric_count}")
        for verification_result in verified_results[:max_verified_metrics]:
            _print_verified_metric_result(
                verification_result,
                show_verified_json=show_verified_json,
            )
        if metric_build_warnings:
            print(f"verified metric warnings: {len(metric_build_warnings)}")
            for warning in metric_build_warnings:
                print(f"  - {warning}")

    if show_json:
        print("json:")
        print(table.model_dump_json(indent=2))

    return verified_metric_count


def _print_parsed_row(parsed_row: ParsedFinancialRow, *, show_parsed_json: bool) -> None:
    print(f"  line {parsed_row.line_number}: {parsed_row.label} -> {parsed_row.values}")
    if show_parsed_json:
        print(parsed_row.model_dump_json(indent=2))


def _print_normalized_row(normalized_row, *, show_normalized_json: bool) -> None:
    print(
        f"  {normalized_row.canonical_name} <= {normalized_row.original_label} "
        f"| values={normalized_row.period_values}"
    )
    if show_normalized_json:
        print(normalized_row.model_dump_json(indent=2))


def _print_mapped_item(mapped_item, *, show_mapped_json: bool) -> None:
    print(f"  {mapped_item.canonical_name}:")
    for key in (
        "group_current",
        "group_previous",
        "group_reported_change_percent",
        "bank_current",
        "bank_previous",
        "bank_reported_change_percent",
    ):
        parsed_value = mapped_item.mapped_values.get(key)
        value = None if parsed_value is None else parsed_value.value
        print(f"    {key}={value}")
    if show_mapped_json:
        print(mapped_item.model_dump_json(indent=2))


def _print_verified_metric_result(
    verification_result,
    *,
    show_verified_json: bool,
) -> None:
    print(f"  {verification_result.metric.metric_name}:")
    print(
        f"    calculated_change_percent={verification_result.calculated_change_percent}"
    )
    print(
        f"    reported_change_percent={verification_result.reported_change_percent}"
    )
    print(
        "    difference_percent_points="
        f"{verification_result.difference_percent_points}"
    )
    print(f"    matches_reported={verification_result.matches_reported}")
    print(f"    direction={verification_result.metric.direction.value}")
    if show_verified_json:
        print(verification_result.model_dump_json(indent=2))


def _build_verified_metric_results_for_mapped_items(
    mapped_items,
    *,
    metric_entity: str,
):
    verified_results = []
    metric_build_warnings: list[str] = []
    for mapped_item in mapped_items:
        if not _is_primary_statement_metric_candidate(mapped_item):
            continue
        try:
            verification_result = build_growth_metric_for_item(
                mapped_item,
                entity_prefix=metric_entity,
            )
        except R11MetricBuildError as error:
            metric_build_warnings.append(str(error))
            continue
        if verification_result is None:
            continue
        verified_results.append(verification_result)
    return verified_results, metric_build_warnings


def _is_primary_statement_metric_candidate(mapped_item: MappedLineItemValues) -> bool:
    statement_type = getattr(mapped_item, "statement_type", None)
    if statement_type is None:
        return True
    if mapped_item.canonical_name in _INCOME_STATEMENT_METRIC_ITEMS:
        return statement_type is FinancialStatementType.INCOME_STATEMENT
    if mapped_item.canonical_name in _BALANCE_SHEET_METRIC_ITEMS:
        return statement_type is FinancialStatementType.BALANCE_SHEET
    return True


def _build_verified_metric_results_for_table(
    *,
    table: ExtractedFinancialTable,
    statement_match: StatementPageMatch | None,
    metric_entity: str,
):
    parsed_rows = parse_financial_rows_from_table(
        table,
        statement_type=statement_match.statement_type if statement_match is not None else None,
    )
    normalized_rows = normalize_parsed_financial_rows(parsed_rows)
    mapped_items = map_comb_six_column_items(normalized_rows)
    mapped_items = _filter_redundant_metric_candidates(
        mapped_items,
        metric_entity=metric_entity,
    )
    return _build_verified_metric_results_for_mapped_items(
        mapped_items,
        metric_entity=metric_entity,
    )


def _build_verified_metric_results_for_tables(
    *,
    tables: list[ExtractedFinancialTable],
    statement_matches_by_key: dict[tuple[str, int | None], StatementPageMatch],
    metric_entity: str,
):
    selected_tables = _select_tables_for_metric_entity(
        tables,
        statement_matches_by_key=statement_matches_by_key,
        metric_entity=metric_entity,
    )
    verified_results = []
    metric_build_warnings: list[str] = []
    for table in selected_tables:
        statement_match = statement_matches_by_key.get((table.table_id, table.page_number))
        table_verified_results, table_metric_build_warnings = _build_verified_metric_results_for_table(
            table=table,
            statement_match=statement_match,
            metric_entity=metric_entity,
        )
        verified_results.extend(table_verified_results)
        metric_build_warnings.extend(table_metric_build_warnings)
    return verified_results, metric_build_warnings


def _select_tables_for_metric_entity(
    tables: list[ExtractedFinancialTable],
    *,
    statement_matches_by_key: dict[tuple[str, int | None], StatementPageMatch],
    metric_entity: str,
) -> list[ExtractedFinancialTable]:
    if metric_entity != "group":
        return list(tables)

    income_statement_tables = [
        table
        for table in tables
        if (
            statement_matches_by_key.get((table.table_id, table.page_number)) is not None
            and statement_matches_by_key[(table.table_id, table.page_number)].statement_type
            is FinancialStatementType.INCOME_STATEMENT
        )
    ]
    if len(income_statement_tables) <= 1:
        return list(tables)

    marked_keys = {
        (table.table_id, table.page_number)
        for table in income_statement_tables
        if _table_has_group_income_statement_markers(table)
    }
    if not marked_keys:
        return list(tables)

    selected_tables: list[ExtractedFinancialTable] = []
    for table in tables:
        statement_match = statement_matches_by_key.get((table.table_id, table.page_number))
        if (
            statement_match is not None
            and statement_match.statement_type is FinancialStatementType.INCOME_STATEMENT
            and (table.table_id, table.page_number) not in marked_keys
        ):
            continue
        selected_tables.append(table)
    return selected_tables


def _table_has_group_income_statement_markers(table: ExtractedFinancialTable) -> bool:
    for row in table.rows:
        text = str(row.get("text", "")).strip().lower()
        if not text:
            continue
        if any(marker in text for marker in _GROUP_INCOME_STATEMENT_MARKERS):
            return True
    return False


def _filter_redundant_metric_candidates(
    mapped_items: list[MappedLineItemValues],
    *,
    metric_entity: str,
) -> list[MappedLineItemValues]:
    current_key = f"{metric_entity}_current"
    previous_key = f"{metric_entity}_previous"
    reported_key = f"{metric_entity}_reported_change_percent"

    grouped_items: dict[tuple[str, float, float] | None, list[MappedLineItemValues]] = {}
    signature_order: list[tuple[str, float, float] | None] = []
    for item in mapped_items:
        signature = _metric_candidate_signature(
            item,
            current_key=current_key,
            previous_key=previous_key,
        )
        if signature not in grouped_items:
            grouped_items[signature] = []
            signature_order.append(signature)
        grouped_items[signature].append(item)

    filtered_items: list[MappedLineItemValues] = []
    for signature in signature_order:
        items_for_signature = grouped_items[signature]
        if signature is None:
            filtered_items.extend(items_for_signature)
            continue
        if any(_has_non_missing_mapped_value(item, reported_key) for item in items_for_signature):
            filtered_items.extend(
                item
                for item in items_for_signature
                if _has_non_missing_mapped_value(item, reported_key)
            )
            continue
        filtered_items.extend(items_for_signature)
    return filtered_items


def _metric_candidate_signature(
    item: MappedLineItemValues,
    *,
    current_key: str,
    previous_key: str,
) -> tuple[str, float, float] | None:
    current_value = _get_optional_mapped_numeric(item, current_key)
    previous_value = _get_optional_mapped_numeric(item, previous_key)
    if current_value is None or previous_value is None:
        return None
    return (item.canonical_name, current_value, previous_value)


def _get_optional_mapped_numeric(item: MappedLineItemValues, key: str) -> float | None:
    parsed_value = item.mapped_values.get(key)
    if parsed_value is None:
        return None
    return parsed_value.value


def _has_non_missing_mapped_value(item: MappedLineItemValues, key: str) -> bool:
    return _get_optional_mapped_numeric(item, key) is not None


def _print_metric_build_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print()
    print("metric build warnings:")
    for warning in warnings:
        print(f"  - {warning}")


def _print_aggregated_metric_result(
    aggregated_result,
    *,
    show_aggregated_json: bool,
) -> None:
    print(f"  {aggregated_result.metric_name}:")
    print(f"    selected_value={aggregated_result.selected_metric.value}")
    print(f"    occurrence_count={aggregated_result.occurrence_count}")
    print(f"    conflict={aggregated_result.conflict}")
    print(
        "    manual_review_required="
        f"{aggregated_result.manual_review_required}"
    )
    print(f"    selected_reason={aggregated_result.selected_reason}")
    print(f"    direction={aggregated_result.selected_metric.direction.value}")
    if aggregated_result.conflict:
        print(f"    conflict_reason={aggregated_result.conflict_reason}")
    if show_aggregated_json:
        print(aggregated_result.model_dump_json(indent=2))


def _print_aggregated_metrics_section(
    aggregated_results,
    *,
    total_raw_verified_metrics: int,
    max_aggregated_metrics: int,
    show_aggregated_json: bool,
) -> None:
    print()
    print("aggregated verified metrics:")
    print(f"  total_raw_verified_metrics: {total_raw_verified_metrics}")
    print(f"  aggregated_metric_count: {len(aggregated_results)}")
    print(f"  has_conflicts: {has_metric_conflicts(aggregated_results)}")
    for aggregated_result in aggregated_results[:max_aggregated_metrics]:
        _print_aggregated_metric_result(
            aggregated_result,
            show_aggregated_json=show_aggregated_json,
        )


def _print_scorecard_section(
    scorecard_result,
    *,
    show_scorecard_json: bool,
) -> None:
    balance_sheet_risk = scorecard_result.scorecard.balance_sheet_risk
    capital_strength = scorecard_result.scorecard.capital_strength
    accounting_risk = scorecard_result.scorecard.accounting_risk

    print()
    print("fundamental scorecard:")
    print(f"  earnings_quality={scorecard_result.scorecard.earnings_quality.value}")
    print(f"  revenue_trend={scorecard_result.scorecard.revenue_trend.value}")
    print(f"  margin_trend={scorecard_result.scorecard.margin_trend.value}")
    print(
        "  balance_sheet_risk="
        f"{None if balance_sheet_risk is None else balance_sheet_risk.value}"
    )
    print(f"  cash_flow_quality={scorecard_result.scorecard.cash_flow_quality.value}")
    print(
        "  capital_strength="
        f"{None if capital_strength is None else capital_strength.value}"
    )
    print(
        "  accounting_risk="
        f"{None if accounting_risk is None else accounting_risk.value}"
    )
    print(
        "  manual_review_required="
        f"{scorecard_result.scorecard.manual_review_required}"
    )
    print(
        "  metric_names_used="
        f"{len(scorecard_result.metric_names_used)} {scorecard_result.metric_names_used}"
    )
    print(
        "  missing_expected_metrics="
        f"{scorecard_result.missing_expected_metrics}"
    )
    print(
        "  manual_review_reasons="
        f"{scorecard_result.manual_review_reasons}"
    )
    print(f"  summary={scorecard_result.scorecard.summary}")
    if show_scorecard_json:
        print(scorecard_result.model_dump_json(indent=2))


def _build_deterministic_analysis_payload(
    *,
    pdf_path: Path,
    tables: list[ExtractedFinancialTable],
    filtered_tables: list[ExtractedFinancialTable],
    shown_tables: list[ExtractedFinancialTable],
    statement_matches: list[StatementPageMatch],
    search_terms: list[str] | None,
    start_page: int | None,
    end_page: int | None,
    verified_metric_results,
    aggregated_metric_results,
    metric_build_warnings: list[str],
    scorecard_build_result,
    scorecard_build_error: str | None,
    generated_at: datetime,
) -> dict[str, object]:
    pages_extracted = [table.page_number for table in tables if table.page_number is not None]
    pages_matched = [
        table.page_number for table in filtered_tables if table.page_number is not None
    ]
    pages_shown = [table.page_number for table in shown_tables if table.page_number is not None]
    notes: list[str] = [
        "Deterministic R11 analysis artifact built from the local manual inspection pipeline."
    ]
    if metric_build_warnings:
        notes.append(
            f"Skipped {len(metric_build_warnings)} invalid metric candidate(s) during deterministic metric assembly."
        )
    if scorecard_build_result is None:
        notes.append("Scorecard build was not available for this deterministic analysis artifact.")
    if scorecard_build_error is not None:
        notes.append(f"Scorecard build error: {scorecard_build_error}")

    return {
        "schema_version": "r11_deterministic_analysis_v1",
        "pdf_path": str(pdf_path.resolve()),
        "extraction_method": tables[0].extraction_method if tables else "unknown",
        "pages_extracted": pages_extracted,
        "pages_matched": pages_matched,
        "pages_shown": pages_shown,
        "active_filters": _active_filters(
            search_terms=search_terms,
            start_page=start_page,
            end_page=end_page,
        ),
        "statement_classifications": [
            match.model_dump(mode="json") for match in statement_matches
        ],
        "verified_metric_results": [
            result.model_dump(mode="json") for result in verified_metric_results
        ],
        "aggregated_metric_results": [
            result.model_dump(mode="json") for result in aggregated_metric_results
        ],
        "metric_build_warnings": metric_build_warnings,
        "scorecard_build_result": None
        if scorecard_build_result is None
        else scorecard_build_result.model_dump(mode="json"),
        "scorecard_build_error": scorecard_build_error,
        "generated_at": generated_at.isoformat(),
        "notes": notes,
    }


def _write_output_json(path: Path, tables: list[ExtractedFinancialTable]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [table.model_dump(mode="json") for table in tables]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    print()
    print(f"saved json: {path.resolve()}")


def _write_output_analysis_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    print()
    print(f"saved analysis json: {path.resolve()}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        pdf_path = Path(args.pdf).expanduser()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise ValueError(f"Local PDF file does not exist: {pdf_path}")
        _validate_page_range(args.start_page, args.end_page)

        extractor = PypdfBaselineExtractor(
            min_non_empty_lines=args.min_non_empty_lines,
        )
        tables = extractor.extract(pdf_path)
        filtered_tables = _filter_tables(
            tables,
            start_page=args.start_page,
            end_page=args.end_page,
            search_terms=args.search,
        )
        shown_tables = _iter_shown_tables(filtered_tables, args.limit_pages)
        statement_matches = locate_statement_pages(filtered_tables)
        statement_matches_by_key = {
            (match.table_id, match.page_number): match for match in statement_matches
        }
        all_verified_results = []
        metric_build_warnings: list[str] = []
        if (
            args.show_verified_metrics
            or args.show_aggregated_metrics
            or args.show_scorecard
            or args.output_analysis_json
        ):
            all_verified_results, metric_build_warnings = _build_verified_metric_results_for_tables(
                tables=shown_tables,
                statement_matches_by_key=statement_matches_by_key,
                metric_entity=args.metric_entity,
            )

        _print_summary(
            pdf_path=pdf_path,
            tables=tables,
            filtered_tables=filtered_tables,
            shown_tables=shown_tables,
            statement_matches=statement_matches,
            search_terms=args.search,
            start_page=args.start_page,
            end_page=args.end_page,
            hide_statement_classification=args.hide_statement_classification,
            total_verified_metrics=(
                len(all_verified_results)
                if (
                    args.show_verified_metrics
                    or args.show_aggregated_metrics
                    or args.show_scorecard
                    or args.output_analysis_json
                )
                else None
            ),
        )
        for table in shown_tables:
            _print_table_preview(
                table=table,
                statement_match=statement_matches_by_key.get((table.table_id, table.page_number)),
                max_lines_per_page=args.max_lines_per_page,
                show_json=args.show_json,
                search_terms=args.search,
                show_matches=args.show_matches,
                context_lines=args.context_lines,
                hide_statement_classification=args.hide_statement_classification,
                show_parsed_rows=args.show_parsed_rows,
                max_parsed_rows=args.max_parsed_rows,
                show_parsed_json=args.show_parsed_json,
                show_normalized_rows=args.show_normalized_rows,
                max_normalized_rows=args.max_normalized_rows,
                show_normalized_json=args.show_normalized_json,
                show_mapped_values=args.show_mapped_values,
                max_mapped_values=args.max_mapped_values,
                show_mapped_json=args.show_mapped_json,
                show_verified_metrics=args.show_verified_metrics,
                metric_entity=args.metric_entity,
                max_verified_metrics=args.max_verified_metrics,
                show_verified_json=args.show_verified_json,
            )

        _print_metric_build_warnings(metric_build_warnings)

        aggregated_results = None
        if args.show_aggregated_metrics or args.show_scorecard or args.output_analysis_json:
            aggregated_results = aggregate_metric_results(all_verified_results)

        if args.show_aggregated_metrics and aggregated_results is not None:
            _print_aggregated_metrics_section(
                aggregated_results,
                total_raw_verified_metrics=len(all_verified_results),
                max_aggregated_metrics=args.max_aggregated_metrics,
                show_aggregated_json=args.show_aggregated_json,
            )

        scorecard_result = None
        scorecard_build_error = None
        if args.show_scorecard and aggregated_results is not None:
            try:
                scorecard_result = build_fundamental_scorecard_from_aggregated_metrics(
                    aggregated_results
                )
            except (R11ScorecardBuildError, ValueError) as error:
                scorecard_build_error = str(error)
                print()
                print(f"scorecard build failed: {scorecard_build_error}")
            else:
                _print_scorecard_section(
                    scorecard_result,
                    show_scorecard_json=args.show_scorecard_json,
                )

        if (
            args.output_analysis_json
            and aggregated_results is not None
            and scorecard_result is None
            and scorecard_build_error is None
        ):
            try:
                scorecard_result = build_fundamental_scorecard_from_aggregated_metrics(
                    aggregated_results
                )
            except (R11ScorecardBuildError, ValueError) as error:
                scorecard_build_error = str(error)

        if args.output_analysis_json:
            analysis_payload = _build_deterministic_analysis_payload(
                pdf_path=pdf_path,
                tables=tables,
                filtered_tables=filtered_tables,
                shown_tables=shown_tables,
                statement_matches=statement_matches,
                search_terms=args.search,
                start_page=args.start_page,
                end_page=args.end_page,
                verified_metric_results=all_verified_results,
                aggregated_metric_results=aggregated_results or [],
                metric_build_warnings=metric_build_warnings,
                scorecard_build_result=scorecard_result,
                scorecard_build_error=scorecard_build_error,
                generated_at=datetime.now(tz=UTC),
            )
            _write_output_analysis_json(
                Path(args.output_analysis_json).expanduser(),
                analysis_payload,
            )

        if args.output_json:
            _write_output_json(Path(args.output_json).expanduser(), filtered_tables)

        return 0
    except (R11ExtractionError, ValueError) as error:
        print(f"R11 pypdf baseline inspection failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 pypdf baseline inspection failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
