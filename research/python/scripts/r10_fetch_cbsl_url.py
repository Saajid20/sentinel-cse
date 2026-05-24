from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import ContextAgent, DeepSeekProvider, R10AnalysisError  # noqa: E402
from sentinel_research.agents.analysis import RetrievedContextAnalyzer  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import CbslUrlDocumentSource, ingest_documents  # noqa: E402
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402

DEFAULT_STORE_PATH = PYTHON_ROOT / ".r10_runtime" / "cbsl_runtime" / "cbsl_documents.jsonl"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch explicit CBSL URLs into the R10 local document store.",
    )
    parser.add_argument(
        "--url",
        action="append",
        required=True,
        help="Explicit CBSL URL to fetch. Can be provided multiple times.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run RetrievedContextAnalyzer after ingestion.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Keyword for retrieval analysis. Can be provided multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Retrieval limit for analysis. Default: 3.",
    )
    parser.add_argument(
        "--store",
        default=str(DEFAULT_STORE_PATH),
        help="Optional JSONL store path.",
    )
    return parser


def _print_ingestion_summary(result, store_path: Path) -> None:
    print("CBSL Runtime Ingestion Summary")
    print(f"fetched_count: {result.fetched_count}")
    print(f"stored_count: {result.stored_count}")
    print(f"skipped_count: {result.skipped_count}")
    print(f"document_ids: {result.document_ids}")
    print(f"errors: {result.errors}")
    print(f"store_path: {store_path}")


def main() -> int:
    args = _build_parser().parse_args()
    store_path = Path(args.store)
    keywords = args.query or ["CBSL", "monetary policy"]

    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)

        source = CbslUrlDocumentSource(args.url)
        store = LocalDocumentStore(store_path)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="cbsl_url_runtime",
            mode="upsert",
        )
        _print_ingestion_summary(ingestion_result, store_path)
        if ingestion_result.errors:
            raise ValueError(
                "CBSL runtime ingestion returned errors: "
                + "; ".join(ingestion_result.errors)
            )

        if not args.analyze:
            return 0

        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            print(
                "R10 CBSL runtime analysis requires DEEPSEEK_API_KEY to be set in the environment."
            )
            return 1

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)
        query = DocumentQuery(keywords=keywords, limit=args.limit)
        analysis = analyzer.analyze(query)

        print("CBSL Runtime Analysis")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (R10AnalysisError, ValueError) as error:
        print(f"R10 CBSL runtime fetch failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 CBSL runtime fetch failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
