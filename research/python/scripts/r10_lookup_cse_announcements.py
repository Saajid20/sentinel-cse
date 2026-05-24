from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.ingestion import CseApiClient, CseApiError  # noqa: E402


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual runtime lookup for CSE announcements via the official CSE API."
    )
    parser.add_argument(
        "--ticker",
        type=_non_empty_value("ticker"),
        help="CSE ticker symbol, for example COMB.N0000.",
    )
    parser.add_argument(
        "--from-date",
        type=_non_empty_value("from_date"),
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--to-date",
        type=_non_empty_value("to_date"),
        help="End date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--announcement-id",
        type=int,
        help="Announcement ID for detail lookup.",
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


def _validate_args(args: argparse.Namespace) -> None:
    if args.announcement_id is not None:
        return

    missing = [
        flag
        for flag, value in (
            ("--ticker", args.ticker),
            ("--from-date", args.from_date),
            ("--to-date", args.to_date),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            "List mode requires "
            + ", ".join(missing)
            + " unless --announcement-id is provided."
        )


def _print_announcement_detail(detail) -> None:
    print("CSE Announcement Detail")
    print(f"announcement_id: {detail.announcement_id}")
    print(f"title: {detail.title}")
    print(f"remarks: {detail.remarks}")
    print(f"date_of_announcement: {detail.date_of_announcement}")
    print(f"symbol: {detail.symbol}")
    print(f"company_name: {detail.company_name}")
    print("documents:")
    if not detail.documents:
        print("  none")
        return
    for index, document in enumerate(detail.documents, start=1):
        print(f"  [{index}]")
        print(f"    file_name: {document.file_name}")
        print(f"    content_type: {document.content_type}")
        print(f"    file_size: {document.file_size}")
        print(f"    full_url: {document.full_url}")


def _print_announcements(ticker: str, from_date: str, to_date: str, announcements: list) -> None:
    print("CSE Announcement Lookup")
    print(f"ticker: {ticker}")
    print(f"from_date: {from_date}")
    print(f"to_date: {to_date}")
    print(f"count: {len(announcements)}")
    if not announcements:
        print("No announcements matched the requested ticker and date range.")
        return
    for index, announcement in enumerate(announcements, start=1):
        print(f"[{index}]")
        print(f"  announcement_id: {announcement.announcement_id}")
        print(f"  id: {announcement.id}")
        print(f"  date_of_announcement: {announcement.date_of_announcement}")
        print(f"  created_date_ms: {announcement.created_date_ms}")
        print(f"  announcement_category: {announcement.announcement_category}")
        print(f"  company: {announcement.company}")
        print(f"  symbol: {announcement.symbol}")
        print(f"  type: {announcement.type}")
        if announcement.remarks:
            print(f"  remarks: {announcement.remarks}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        _validate_args(args)
        client = CseApiClient(
            base_url=args.base_url,
            timeout=args.timeout,
        )

        if args.announcement_id is not None:
            detail = client.get_announcement_detail(args.announcement_id)
            _print_announcement_detail(detail)
            return 0

        announcements = client.get_announcements_by_company(
            args.ticker,
            args.from_date,
            args.to_date,
        )
        _print_announcements(args.ticker, args.from_date, args.to_date, announcements)
        return 0
    except (CseApiError, ValueError) as error:
        print(f"R10 CSE announcements lookup failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CSE announcements lookup failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
