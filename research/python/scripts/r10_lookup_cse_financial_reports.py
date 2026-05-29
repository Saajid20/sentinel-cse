from __future__ import annotations

import argparse
from datetime import UTC, datetime, date
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.ingestion import (  # noqa: E402
    CseApiClient,
    CseApiError,
    CseFinancialReport,
)


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _parse_iso_date(name: str):
    def _parser(value: str) -> date:
        normalized = value.strip()
        try:
            return date.fromisoformat(normalized)
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                f"{name} must be in YYYY-MM-DD format"
            ) from error

    return _parser


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
        description="Manual runtime lookup for CSE financial report candidates."
    )
    parser.add_argument(
        "--ticker",
        type=_non_empty_value("ticker"),
        help="Optional ticker filter, for example DIAL or DIAL.N0000.",
    )
    parser.add_argument(
        "--from-date",
        type=_parse_iso_date("from-date"),
        help="Optional lower date bound in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--to-date",
        type=_parse_iso_date("to-date"),
        help="Optional upper date bound in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--text",
        type=_non_empty_value("text"),
        help="Optional substring filter against file text, name, symbol, or path.",
    )
    parser.add_argument(
        "--top",
        type=_positive_int("top"),
        default=20,
        help="Maximum number of matching report candidates to print.",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.cse.lk/api",
        type=_non_empty_value("base_url"),
        help="CSE API base URL.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    return parser


def _normalize_bare_ticker(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    return normalized.split(".", maxsplit=1)[0]


def _report_effective_date(report: CseFinancialReport) -> date | None:
    if report.manual_date_ms is not None:
        return datetime.fromtimestamp(report.manual_date_ms / 1000.0, tz=UTC).date()
    for text_value in (report.uploaded_date, report.authorized_date):
        if not text_value:
            continue
        try:
            return datetime.strptime(text_value, "%d %b %Y %I:%M:%S %p").date()
        except ValueError:
            continue
    return None


def _matches_ticker(report: CseFinancialReport, ticker: str | None) -> bool:
    if ticker is None:
        return True
    return _normalize_bare_ticker(report.symbol) == _normalize_bare_ticker(ticker)


def _matches_text(report: CseFinancialReport, text_filter: str | None) -> bool:
    if text_filter is None:
        return True
    normalized_filter = text_filter.strip().lower()
    haystack = " ".join(
        value
        for value in (report.file_text, report.name, report.symbol, report.path)
        if value
    ).lower()
    return normalized_filter in haystack


def _matches_date_range(
    report: CseFinancialReport,
    from_date: date | None,
    to_date: date | None,
) -> bool:
    if from_date is None and to_date is None:
        return True
    report_date = _report_effective_date(report)
    if report_date is None:
        return False
    if from_date is not None and report_date < from_date:
        return False
    if to_date is not None and report_date > to_date:
        return False
    return True


def filter_financial_reports(
    reports: list[CseFinancialReport],
    *,
    ticker: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    text_filter: str | None = None,
) -> list[CseFinancialReport]:
    return [
        report
        for report in reports
        if _matches_ticker(report, ticker)
        and _matches_date_range(report, from_date, to_date)
        and _matches_text(report, text_filter)
    ]


def _print_report(report: CseFinancialReport, *, index: int) -> None:
    print(f"[{index}]")
    print(f"  id: {report.id}")
    print(f"  symbol: {report.symbol}")
    print(f"  company: {report.name}")
    print(f"  manual_date_ms: {report.manual_date_ms}")
    print(f"  uploaded_date: {report.uploaded_date}")
    print(f"  authorized_date: {report.authorized_date}")
    print(f"  file_text: {report.file_text}")
    print(f"  path: {report.path}")
    print(f"  full_url: {report.full_url}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        client = CseApiClient(
            base_url=args.base_url,
            timeout=args.timeout,
        )
        reports = client.get_financial_reports()
        filtered = filter_financial_reports(
            reports,
            ticker=args.ticker,
            from_date=args.from_date,
            to_date=args.to_date,
            text_filter=args.text,
        )
        shown = filtered[: args.top]

        print("CSE Financial Reports Lookup")
        print(f"ticker: {args.ticker or '-'}")
        print(f"from_date: {args.from_date.isoformat() if args.from_date else '-'}")
        print(f"to_date: {args.to_date.isoformat() if args.to_date else '-'}")
        print(f"text: {args.text or '-'}")
        print(f"count: {len(filtered)}")
        if not shown:
            print("No financial reports matched the requested filters.")
            return 0

        for index, report in enumerate(shown, start=1):
            _print_report(report, index=index)
        return 0
    except (CseApiError, ValueError) as error:
        print(f"R10 CSE financial reports lookup failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CSE financial reports lookup failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
