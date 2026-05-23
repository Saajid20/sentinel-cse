from __future__ import annotations

import os
import sys
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
    DirectoryTextDocumentSource,
    ingest_documents,
)
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402

RUNTIME_DIR = PYTHON_ROOT / ".r10_runtime" / "manual_file_ingestion"
STORE_PATH = RUNTIME_DIR / "manual_file_docs.jsonl"
SCRIPT_FILE_NAMES = (
    "cbsl_rate_cut_banking.txt",
    "xyz_dividend_disclosure.md",
    "low_impact_retail_expansion.html",
    "manual_file_docs.jsonl",
)


def _clear_script_runtime_files(runtime_dir: Path) -> None:
    for file_name in SCRIPT_FILE_NAMES:
        path = runtime_dir / file_name
        if path.exists() and path.is_file():
            path.unlink()


def _write_sample_files(runtime_dir: Path) -> None:
    (runtime_dir / "cbsl_rate_cut_banking.txt").write_text(
        (
            "CBSL cut the SDFR and SLFR by 50 basis points to support liquidity conditions.\n"
            "The policy easing may improve credit demand and funding flexibility, but banking "
            "sector margins could compress during the repricing period.\n"
        ),
        encoding="utf-8",
    )
    (runtime_dir / "xyz_dividend_disclosure.md").write_text(
        (
            "# XYZ.N0000 Final Dividend Update\n\n"
            "XYZ.N0000 disclosed an increased final dividend after reporting stable operating "
            "cash flow and disciplined working-capital management.\n"
        ),
        encoding="utf-8",
    )
    (runtime_dir / "low_impact_retail_expansion.html").write_text(
        (
            "<html><head><style>.hidden{display:none}</style>"
            "<script>console.log('ignore me');</script></head><body>"
            "<h1>Retail Expansion Note</h1>"
            "<p>A small retailer opened one additional outlet in a suburban area.</p>"
            "<p>The update suggests limited local growth and no material market impact.</p>"
            "</body></html>"
        ),
        encoding="utf-8",
    )


def _print_ingestion_summary(result) -> None:
    print("Ingestion Summary")
    print(f"fetched_count: {result.fetched_count}")
    print(f"stored_count: {result.stored_count}")
    print(f"skipped_count: {result.skipped_count}")
    print(f"document_ids: {result.document_ids}")
    print(f"errors: {result.errors}")


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "R10 manual file ingestion smoke test requires DEEPSEEK_API_KEY "
            "to be set in the environment."
        )
        return 1

    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        _clear_script_runtime_files(RUNTIME_DIR)
        _write_sample_files(RUNTIME_DIR)

        source = DirectoryTextDocumentSource(
            RUNTIME_DIR,
            source_type=SourceType.NEWS,
            default_sectors_hint=["BANKING", "CONSUMER"],
        )
        store = LocalDocumentStore(STORE_PATH)
        ingestion_result = ingest_documents(
            source,
            store,
            source_name="manual_file_smoke",
            mode="upsert",
        )
        _print_ingestion_summary(ingestion_result)
        if ingestion_result.errors:
            raise ValueError(
                "Manual file ingestion returned errors: "
                + "; ".join(ingestion_result.errors)
            )

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)

        query = DocumentQuery(
            keywords=["CBSL", "rate cut", "banking"],
            sectors=["BANKING"],
            limit=1,
        )
        analysis = analyzer.analyze(query)

        print("R10 Manual File Ingestion Smoke Test")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (R10AnalysisError, ValueError) as error:
        print(f"R10 manual file ingestion smoke test failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 manual file ingestion smoke test failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
