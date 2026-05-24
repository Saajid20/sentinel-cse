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

DEFAULT_STORE_PATH = (
    PYTHON_ROOT / ".r10_runtime" / "cse_disclosures" / "cse_disclosures.jsonl"
)


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually ingest and analyze a local CSE corporate disclosure PDF with R10."
    )
    parser.add_argument("--pdf", required=True, help="Path to a local CSE disclosure PDF.")
    parser.add_argument(
        "--ticker",
        required=True,
        type=_non_empty_value("ticker"),
        help="CSE ticker symbol, for example COMB.N0000.",
    )
    parser.add_argument(
        "--company",
        required=True,
        type=_non_empty_value("company"),
        help="Company name or short name.",
    )
    parser.add_argument(
        "--announcement-type",
        required=True,
        type=_non_empty_value("announcement_type"),
        help="Disclosure type, for example DIVIDEND or EARNINGS.",
    )
    parser.add_argument("--title", help="Optional title override.")
    parser.add_argument("--url", help="Optional original CSE disclosure URL.")
    parser.add_argument(
        "--published-at",
        type=_parse_iso_timestamp,
        help="Optional published timestamp in ISO-8601 format.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Retrieval keyword. May be passed multiple times.",
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
        print(
            "R10 CSE disclosure PDF verification requires DEEPSEEK_API_KEY to be set in the environment."
        )
        return 1

    try:
        pdf_path = Path(args.pdf).expanduser()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise ValueError(f"Local CSE disclosure PDF does not exist: {pdf_path}")

        announcement_type = args.announcement_type.strip().upper()
        title = args.title or f"{args.ticker} {announcement_type} disclosure"

        store_path = Path(args.store).expanduser()
        store_path.parent.mkdir(parents=True, exist_ok=True)

        source = PdfFileDocumentSource(
            pdf_path,
            source_type=SourceType.CSE_DISCLOSURE,
            title=title,
            url=args.url,
            published_at=args.published_at,
            tickers_hint=[args.ticker],
            sectors_hint=[],
            metadata={
                "source": "CSE",
                "ticker": args.ticker,
                "company": args.company,
                "announcement_type": announcement_type,
            },
        )
        store = LocalDocumentStore(store_path)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="cse_disclosure_pdf_runtime",
            mode="upsert",
        )
        _print_ingestion_summary(result=ingestion_result, store_path=store_path)
        if ingestion_result.errors:
            print("R10 CSE disclosure PDF verification failed during ingestion.")
            return 2
        if ingestion_result.stored_count == 0:
            print("R10 CSE disclosure PDF verification stored no documents.")
            return 2

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)

        query = DocumentQuery(
            keywords=args.query or [args.ticker, args.company, announcement_type],
            tickers=[args.ticker],
            limit=args.limit,
        )
        analysis = analyzer.analyze(query)

        print("R10 CSE Disclosure PDF Verification")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (PdfExtractionError, ValueError, R10AnalysisError) as error:
        print(f"R10 CSE disclosure PDF verification failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CSE disclosure PDF verification failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
