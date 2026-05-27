from __future__ import annotations

import argparse
import hashlib
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import SourceType  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    PdfExtractionError,
    PdfFileDocumentSource,
    ingest_documents,
)

DEFAULT_DOWNLOAD_DIR = PYTHON_ROOT / ".r10_runtime" / "cse_report_pdfs"
DEFAULT_STORE_PATH = DEFAULT_DOWNLOAD_DIR / "cse_report_documents.jsonl"
EXPECTED_CSE_CDN_HOST = "cdn.cse.lk"


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO timestamp {value!r}. Expected ISO-8601 format."
        ) from error


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _quote_url_path(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    quoted_path = urllib.parse.quote(parts.path, safe="/%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, quoted_path, parts.query, parts.fragment))


def _sanitize_filename_component(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "document"


def _validate_cse_pdf_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("--url must not be empty")

    parts = urllib.parse.urlsplit(normalized)
    if parts.scheme.lower() != "https":
        raise ValueError("CSE PDF URL must use https")

    if parts.netloc.lower() != EXPECTED_CSE_CDN_HOST:
        raise ValueError(
            f"CSE PDF URL must point to {EXPECTED_CSE_CDN_HOST}; got {parts.netloc or '<missing host>'}"
        )

    if not parts.path.lower().endswith(".pdf"):
        raise ValueError("CSE PDF URL path must end with .pdf")

    return normalized


def _build_download_path(download_dir: Path, *, ticker: str, url: str) -> Path:
    parts = urllib.parse.urlsplit(url)
    path_name = Path(parts.path).name or "cse_report.pdf"
    suffix = Path(path_name).suffix or ".pdf"
    stem = Path(path_name).stem or "cse_report"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    file_name = (
        f"cse_report_{_sanitize_filename_component(ticker)}_"
        f"{_sanitize_filename_component(stem)}_{url_hash}{suffix}"
    )
    return download_dir / file_name


def _download_headers() -> dict[str, str]:
    return {
        "User-Agent": "Sentinel-CSE-R10/0.1",
        "Accept": "application/pdf, application/octet-stream, */*",
        "Origin": "https://www.cse.lk",
        "Referer": "https://www.cse.lk/",
        "Connection": "close",
    }


def _download_pdf(url: str, destination: Path, *, timeout: float) -> None:
    encoded_url = _quote_url_path(url)
    request = urllib.request.Request(encoded_url, headers=_download_headers(), method="GET")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionResetError) as error:
        raise ValueError(f"Failed to download CSE PDF {url}: {error}") from error

    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        if callable(getcode):
            status = getcode()
    if status != 200:
        raise ValueError(f"Failed to download CSE PDF {url}: HTTP {status}")

    content = response.read()
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"Downloaded file does not appear to be a PDF: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and ingest a CSE-hosted PDF URL into the local R10 document store."
    )
    parser.add_argument(
        "--url",
        required=True,
        type=_non_empty_value("url"),
        help="Explicit HTTPS CSE CDN PDF URL.",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        type=_non_empty_value("ticker"),
        help="CSE ticker symbol, for example SAMP.N0000.",
    )
    parser.add_argument(
        "--company",
        type=_non_empty_value("company"),
        help="Optional company name.",
    )
    parser.add_argument(
        "--announcement-type",
        type=_non_empty_value("announcement_type"),
        help="Optional disclosure or report type.",
    )
    parser.add_argument(
        "--title",
        type=_non_empty_value("title"),
        help="Optional title override.",
    )
    parser.add_argument(
        "--published-at",
        type=_parse_iso_timestamp,
        help="Optional published timestamp in ISO-8601 format.",
    )
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE_PATH),
        help="Path to the local JSONL document store.",
    )
    parser.add_argument(
        "--download-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help="Directory for downloaded CSE report PDFs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    return parser


def _print_ingestion_summary(
    *,
    result,
    store_path: Path,
    download_path: Path,
    ticker: str,
    title: str,
    source_url: str,
) -> None:
    print("R10 CSE PDF URL Ingestion")
    print(f"ticker: {ticker}")
    print(f"title: {title}")
    print(f"source_url: {source_url}")
    print(f"downloaded PDF path: {download_path}")
    print(f"store path: {store_path}")
    print(f"document_ids: {result.document_ids}")
    print(f"fetched_count: {result.fetched_count}")
    print(f"stored_count: {result.stored_count}")
    print(f"skipped_count: {result.skipped_count}")
    print(f"errors: {result.errors}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        resolved_url = _validate_cse_pdf_url(args.url)
        download_dir = Path(args.download_dir).expanduser()
        store_path = Path(args.store).expanduser()
        download_path = _build_download_path(download_dir, ticker=args.ticker, url=resolved_url)

        _download_pdf(resolved_url, download_path, timeout=args.timeout)

        resolved_title = args.title or Path(urllib.parse.urlsplit(resolved_url).path).stem or f"{args.ticker} CSE report"
        announcement_type = args.announcement_type.strip().upper() if args.announcement_type else None

        source = PdfFileDocumentSource(
            download_path,
            source_type=SourceType.CSE_DISCLOSURE,
            title=resolved_title,
            url=resolved_url,
            published_at=args.published_at,
            tickers_hint=[args.ticker],
            sectors_hint=[],
            metadata={
                "source": "CSE",
                "ticker": args.ticker,
                "company": args.company,
                "announcement_type": announcement_type,
                "source_url": resolved_url,
            },
        )
        store = LocalDocumentStore(store_path)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="cse_pdf_url_runtime",
            mode="upsert",
        )
        _print_ingestion_summary(
            result=ingestion_result,
            store_path=store_path,
            download_path=download_path,
            ticker=args.ticker,
            title=resolved_title,
            source_url=resolved_url,
        )
        if ingestion_result.errors:
            raise ValueError(
                "CSE PDF URL ingestion returned errors: " + "; ".join(ingestion_result.errors)
            )
        if ingestion_result.stored_count == 0:
            raise ValueError("CSE PDF URL ingestion stored no documents.")
        return 0
    except (PdfExtractionError, ValueError) as error:
        print(f"R10 CSE PDF URL ingestion failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CSE PDF URL ingestion failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
