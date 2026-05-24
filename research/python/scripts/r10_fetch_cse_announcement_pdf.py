from __future__ import annotations

import argparse
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import (  # noqa: E402
    ContextAgent,
    DeepSeekProvider,
    R10AnalysisError,
    SourceType,
)
from sentinel_research.agents.analysis import RetrievedContextAnalyzer  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    CseApiClient,
    CseApiError,
    PdfExtractionError,
    PdfFileDocumentSource,
    ingest_documents,
)
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402

DEFAULT_STORE_PATH = (
    PYTHON_ROOT / ".r10_runtime" / "cse_announcements" / "cse_announcement_documents.jsonl"
)
DEFAULT_DOWNLOAD_DIR = PYTHON_ROOT / ".r10_runtime" / "cse_announcements" / "pdfs"


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one selected CSE announcement PDF via the CSE API and optionally analyze it with R10."
    )
    parser.add_argument(
        "--announcement-id",
        required=True,
        type=int,
        help="CSE announcement ID.",
    )
    parser.add_argument(
        "--doc-index",
        type=int,
        default=1,
        help="1-based document index in the announcement detail response. Default: 1.",
    )
    parser.add_argument(
        "--ticker",
        type=_non_empty_value("ticker"),
        help="Optional full CSE ticker, for example JKH.N0000.",
    )
    parser.add_argument(
        "--company",
        type=_non_empty_value("company"),
        help="Optional company name override.",
    )
    parser.add_argument(
        "--announcement-type",
        type=_non_empty_value("announcement_type"),
        help="Optional announcement type override.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run RetrievedContextAnalyzer after ingestion.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Retrieval keyword for analysis. May be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum documents to analyze. Default: 1.",
    )
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE_PATH),
        help="Path to the local JSONL document store.",
    )
    parser.add_argument(
        "--download-dir",
        default=str(DEFAULT_DOWNLOAD_DIR),
        help="Directory for downloaded announcement PDFs.",
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


def _quote_url_path(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    quoted_path = urllib.parse.quote(parts.path, safe="/%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, quoted_path, parts.query, parts.fragment))


def _is_pdf_document(document) -> bool:
    content_type = (document.content_type or "").lower()
    file_name = (document.file_name or "").lower()
    full_url = (document.full_url or "").lower()
    return "application/pdf" in content_type or file_name.endswith(".pdf") or full_url.endswith(".pdf")


def _sanitize_filename_component(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = sanitized.strip("._")
    return sanitized or "document"


def _build_download_path(download_dir: Path, announcement_id: int, doc_index: int, document) -> Path:
    base_name = document.file_name or Path(urllib.parse.urlsplit(document.full_url).path).name or "cse_document.pdf"
    suffix = Path(base_name).suffix or ".pdf"
    stem = Path(base_name).stem or "cse_document"
    doc_identifier = document.id if document.id is not None else doc_index
    file_name = (
        f"announcement_{announcement_id}_doc_{doc_identifier}_"
        f"{_sanitize_filename_component(stem)}{suffix}"
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
        raise ValueError(f"Failed to download CSE announcement PDF {url}: {error}") from error

    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        if callable(getcode):
            status = getcode()
    if status != 200:
        raise ValueError(f"Failed to download CSE announcement PDF {url}: HTTP {status}")

    content = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def _print_detail_summary(detail) -> None:
    print("CSE Announcement Detail")
    print(f"announcement_id: {detail.announcement_id}")
    print(f"title: {detail.title}")
    print(f"remarks: {detail.remarks}")
    print(f"date_of_announcement: {detail.date_of_announcement}")
    print(f"symbol: {detail.symbol}")
    print(f"company_name: {detail.company_name}")
    print("available documents:")
    if not detail.documents:
        print("  none")
        return
    for index, document in enumerate(detail.documents, start=1):
        print(f"  [{index}]")
        print(f"    id: {document.id}")
        print(f"    file_name: {document.file_name}")
        print(f"    content_type: {document.content_type}")
        print(f"    file_size: {document.file_size}")
        print(f"    full_url: {document.full_url}")


def _print_ingestion_summary(*, result, store_path: Path, download_path: Path) -> None:
    print("Ingestion Summary")
    print(f"fetched_count: {result.fetched_count}")
    print(f"stored_count: {result.stored_count}")
    print(f"skipped_count: {result.skipped_count}")
    print(f"document_ids: {result.document_ids}")
    print(f"errors: {result.errors}")
    print(f"store path: {store_path}")
    print(f"downloaded PDF path: {download_path}")


def _default_query_keywords(*, ticker: str | None, company: str | None, title: str | None, announcement_id: int) -> list[str]:
    values = [ticker, company, title, str(announcement_id)]
    keywords: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = value.strip()
        if normalized and normalized not in keywords:
            keywords.append(normalized)
    return keywords


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.doc_index <= 0:
            raise ValueError("--doc-index must be greater than 0")

        client = CseApiClient(
            base_url=args.base_url,
            timeout=args.timeout,
        )
        detail = client.get_announcement_detail(args.announcement_id)
        _print_detail_summary(detail)

        if not detail.documents:
            raise ValueError(f"No documents available for announcement_id={args.announcement_id}")
        if args.doc_index > len(detail.documents):
            raise ValueError(
                f"--doc-index {args.doc_index} is out of range for {len(detail.documents)} available document(s)"
            )

        selected_document = detail.documents[args.doc_index - 1]
        if not _is_pdf_document(selected_document):
            raise ValueError(
                f"Selected document at index {args.doc_index} does not appear to be a PDF: "
                f"{selected_document.file_name or selected_document.full_url}"
            )

        resolved_ticker = args.ticker or detail.symbol
        resolved_company = args.company or detail.company_name
        resolved_announcement_type = args.announcement_type or detail.title or "CSE_DISCLOSURE"

        download_dir = Path(args.download_dir).expanduser()
        download_path = _build_download_path(
            download_dir,
            args.announcement_id,
            args.doc_index,
            selected_document,
        )
        _download_pdf(selected_document.full_url, download_path, timeout=args.timeout)

        store_path = Path(args.store).expanduser()
        store_path.parent.mkdir(parents=True, exist_ok=True)

        source = PdfFileDocumentSource(
            download_path,
            source_type=SourceType.CSE_DISCLOSURE,
            title=detail.title or selected_document.file_name or "CSE disclosure",
            url=selected_document.full_url,
            published_at=None,
            tickers_hint=[resolved_ticker] if resolved_ticker else [],
            sectors_hint=[],
            metadata={
                "source": "CSE",
                "announcement_id": args.announcement_id,
                "cse_symbol": detail.symbol,
                "ticker": resolved_ticker,
                "company": resolved_company,
                "announcement_type": resolved_announcement_type,
                "remarks": detail.remarks,
                "document_id": selected_document.id,
                "file_name": selected_document.file_name,
            },
        )
        store = LocalDocumentStore(store_path)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="cse_announcement_pdf_runtime",
            mode="upsert",
        )
        _print_ingestion_summary(
            result=ingestion_result,
            store_path=store_path,
            download_path=download_path,
        )
        if ingestion_result.errors:
            raise ValueError(
                "CSE announcement PDF ingestion returned errors: "
                + "; ".join(ingestion_result.errors)
            )
        if ingestion_result.stored_count == 0:
            raise ValueError("CSE announcement PDF ingestion stored no documents.")

        if not args.analyze:
            return 0

        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            print("R10 CSE announcement PDF analysis requires DEEPSEEK_API_KEY to be set in the environment.")
            return 1

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)
        query = DocumentQuery(
            keywords=args.query
            or _default_query_keywords(
                ticker=resolved_ticker,
                company=resolved_company,
                title=detail.title,
                announcement_id=args.announcement_id,
            ),
            tickers=[resolved_ticker] if resolved_ticker else [],
            limit=args.limit,
        )
        analysis = analyzer.analyze(query)

        print("R10 CSE Announcement PDF Analysis")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (CseApiError, PdfExtractionError, ValueError, R10AnalysisError) as error:
        print(f"R10 CSE announcement PDF fetch failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CSE announcement PDF fetch failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
