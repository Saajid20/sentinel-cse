from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
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
    PdfExtractionError,
    PdfFileDocumentSource,
    ingest_documents,
)
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402

DEFAULT_STORE_PATH = PYTHON_ROOT / ".r10_runtime" / "local_pdf" / "local_pdf_documents.jsonl"
DEFAULT_QUERIES = ["CBSL", "PMI"]


def _parse_source_type(value: str) -> SourceType:
    normalized = value.strip().upper()
    try:
        return SourceType[normalized]
    except KeyError as error:
        allowed = ", ".join(source_type.value for source_type in SourceType)
        raise argparse.ArgumentTypeError(
            f"Invalid source type {value!r}. Expected one of: {allowed}"
        ) from error


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual local PDF smoke test for the Sentinel-CSE R10 local RAG pipeline."
    )
    parser.add_argument("--pdf", required=True, help="Path to a local PDF file.")
    parser.add_argument("--title", help="Optional title override.")
    parser.add_argument(
        "--source-type",
        default=SourceType.CBSL,
        type=_parse_source_type,
        help="Source type for the ingested document.",
    )
    parser.add_argument("--url", help="Optional original source URL.")
    parser.add_argument(
        "--published-at",
        type=_parse_iso_timestamp,
        help="Optional source published timestamp in ISO-8601 format.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Keyword query term. May be passed multiple times.",
    )
    parser.add_argument(
        "--sector",
        action="append",
        default=[],
        help="Sector hint for retrieval. May be passed multiple times.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Ticker hint for retrieval. May be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, default=1, help="Maximum documents to analyze.")
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE_PATH),
        help="Path to the local JSONL document store.",
    )
    return parser


def _print_ingestion_summary(*, result, store_path: Path) -> None:
    print("Ingestion Summary")
    print(f"fetched_count: {result.fetched_count}")
    print(f"stored_count: {result.stored_count}")
    print(f"skipped_count: {result.skipped_count}")
    print(f"document_ids: {result.document_ids}")
    print(f"errors: {result.errors}")
    print(f"store path: {store_path}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("R10 local PDF smoke test requires DEEPSEEK_API_KEY to be set in the environment.")
        return 1

    try:
        pdf_path = Path(args.pdf).expanduser()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise ValueError(f"Local PDF file does not exist: {pdf_path}")

        store_path = Path(args.store).expanduser()
        store_path.parent.mkdir(parents=True, exist_ok=True)

        source = PdfFileDocumentSource(
            pdf_path,
            source_type=args.source_type,
            title=args.title,
            url=args.url,
            published_at=args.published_at,
            tickers_hint=args.ticker,
            sectors_hint=args.sector,
        )
        store = LocalDocumentStore(store_path)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="local_pdf_runtime",
            mode="upsert",
        )
        _print_ingestion_summary(result=ingestion_result, store_path=store_path)
        if ingestion_result.errors:
            print("R10 local PDF smoke test failed during ingestion.")
            return 2
        if ingestion_result.stored_count == 0:
            print("R10 local PDF smoke test stored no documents.")
            return 2

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)

        query = DocumentQuery(
            keywords=args.query or list(DEFAULT_QUERIES),
            sectors=args.sector,
            tickers=args.ticker,
            limit=args.limit,
        )
        analysis = analyzer.analyze(query)

        print("R10 Local PDF RAG Smoke Test")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (PdfExtractionError, ValueError, R10AnalysisError) as error:
        print(f"R10 local PDF smoke test failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 local PDF smoke test failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
