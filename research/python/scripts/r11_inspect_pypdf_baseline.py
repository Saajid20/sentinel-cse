from __future__ import annotations

import argparse
import json
import sys
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
from sentinel_research.agents.r11.schemas import ExtractedFinancialTable  # noqa: E402


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
) -> None:
    pages = [table.page_number for table in tables if table.page_number is not None]
    filtered_pages = [
        table.page_number for table in filtered_tables if table.page_number is not None
    ]
    shown_pages = [table.page_number for table in shown_tables if table.page_number is not None]
    extraction_method = tables[0].extraction_method if tables else "unknown"
    active_filters: list[str] = []
    if start_page is not None:
        active_filters.append(f"start_page>={start_page}")
    if end_page is not None:
        active_filters.append(f"end_page<={end_page}")
    normalized_terms = _normalize_search_terms(search_terms)
    if normalized_terms:
        active_filters.append(f"search={normalized_terms}")

    print("R11 pypdf Baseline Inspection")
    print(f"PDF path: {pdf_path.resolve()}")
    print(f"total extracted page count: {len(tables)}")
    print(f"filtered page count: {len(filtered_tables)}")
    print(f"extraction method: {extraction_method}")
    print(f"active filters: {active_filters or ['none']}")
    print(f"pages extracted: {pages}")
    print(f"pages matched: {filtered_pages}")
    print(f"pages shown/saved: {shown_pages}")
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
) -> None:
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

    if show_parsed_rows:
        parsed_rows = parse_financial_rows_from_table(
            table,
            statement_type=statement_match.statement_type if statement_match is not None else None,
        )
        print(f"parsed financial rows: {len(parsed_rows)}")
        for parsed_row in parsed_rows[:max_parsed_rows]:
            _print_parsed_row(parsed_row, show_parsed_json=show_parsed_json)

    if show_json:
        print("json:")
        print(table.model_dump_json(indent=2))


def _print_parsed_row(parsed_row: ParsedFinancialRow, *, show_parsed_json: bool) -> None:
    print(f"  line {parsed_row.line_number}: {parsed_row.label} -> {parsed_row.values}")
    if show_parsed_json:
        print(parsed_row.model_dump_json(indent=2))


def _write_output_json(path: Path, tables: list[ExtractedFinancialTable]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [table.model_dump(mode="json") for table in tables]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    print()
    print(f"saved json: {path.resolve()}")


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
