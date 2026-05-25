from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.extraction import (  # noqa: E402
    PypdfBaselineExtractor,
    R11ExtractionError,
)
from sentinel_research.agents.r11.schemas import ExtractedFinancialTable  # noqa: E402


def _positive_int(name: str):
    def _parser(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from error
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{name} must be > 0")
        return parsed

    return _parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual inspection script for the R11 pypdf baseline table/text extractor."
    )
    parser.add_argument("--pdf", required=True, help="Path to a local PDF file.")
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
        "--min-non-empty-lines",
        type=_positive_int("min_non_empty_lines"),
        default=2,
        help="Minimum non-empty lines required for a page to be included.",
    )
    return parser


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
) -> None:
    pages = [table.page_number for table in tables if table.page_number is not None]
    extraction_method = tables[0].extraction_method if tables else "unknown"

    print("R11 pypdf Baseline Inspection")
    print(f"PDF path: {pdf_path.resolve()}")
    print(f"extracted table/page count: {len(tables)}")
    print(f"extraction method: {extraction_method}")
    print(f"pages included: {pages}")


def _print_table_preview(
    *,
    table: ExtractedFinancialTable,
    max_lines_per_page: int,
    show_json: bool,
) -> None:
    print()
    print(f"table_id: {table.table_id}")
    print(f"page_number: {table.page_number}")
    print(f"extraction_confidence: {table.extraction_confidence.value}")
    print(f"line count: {len(table.rows)}")
    print(f"first {min(len(table.rows), max_lines_per_page)} lines:")

    for row in table.rows[:max_lines_per_page]:
        print(f"  {row['line_number']}: {row['text']}")

    if show_json:
        print("json:")
        print(table.model_dump_json(indent=2))


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

        extractor = PypdfBaselineExtractor(
            min_non_empty_lines=args.min_non_empty_lines,
        )
        tables = extractor.extract(pdf_path)
        shown_tables = _iter_shown_tables(tables, args.limit_pages)

        _print_summary(pdf_path=pdf_path, tables=tables)
        for table in shown_tables:
            _print_table_preview(
                table=table,
                max_lines_per_page=args.max_lines_per_page,
                show_json=args.show_json,
            )

        if args.output_json:
            _write_output_json(Path(args.output_json).expanduser(), tables)

        return 0
    except (R11ExtractionError, ValueError) as error:
        print(f"R11 pypdf baseline inspection failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 pypdf baseline inspection failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
