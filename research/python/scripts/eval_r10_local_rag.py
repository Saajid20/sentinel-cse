from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import ContextAgent, DeepSeekProvider, R10AnalysisError  # noqa: E402
from sentinel_research.agents.analysis import RetrievedContextAnalyzer  # noqa: E402
from sentinel_research.agents.documents import (  # noqa: E402
    LocalDocumentStore,
    SourceDocument,
    build_normalized_text,
)
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402

RUNTIME_STORE_PATH = PYTHON_ROOT / ".r10_runtime" / "local_rag_smoke_docs.jsonl"


def _make_source_documents() -> list[SourceDocument]:
    retrieved_at = datetime.now(timezone.utc)
    documents: list[SourceDocument] = []

    cbsl_raw_text = (
        "COLOMBO - The Central Bank of Sri Lanka reduced policy rates by 50 basis points "
        "after citing softer inflation and improved liquidity. Market participants said "
        "the move could support credit demand while leaving banks exposed to some margin "
        "compression during the adjustment period."
    )
    documents.append(
        SourceDocument(
            document_id="cbsl-rate-cut-banking",
            source_type="CBSL",
            title="CBSL rate cut brings mixed implications for banking shares",
            url="https://example.invalid/cbsl-rate-cut-banking",
            published_at=datetime(2026, 5, 23, 8, 30, tzinfo=timezone.utc),
            retrieved_at=retrieved_at,
            raw_text=cbsl_raw_text,
            normalized_text=build_normalized_text(cbsl_raw_text),
            tickers_hint=[],
            sectors_hint=["BANKING"],
            metadata={"scenario": "macro_rate_cut", "priority": 1},
        )
    )

    dividend_raw_text = (
        "COLOMBO - XYZ.N0000 announced a final cash dividend above the prior year after "
        "steady operating cash flow and resilient domestic demand. The disclosure was "
        "specific to the issuer and pointed to improved shareholder payouts."
    )
    documents.append(
        SourceDocument(
            document_id="xyz-dividend-announcement",
            source_type="CSE_DISCLOSURE",
            title="XYZ.N0000 final dividend announcement",
            url="https://example.invalid/xyz-dividend-announcement",
            published_at=datetime(2026, 5, 21, 10, 15, tzinfo=timezone.utc),
            retrieved_at=retrieved_at,
            raw_text=dividend_raw_text,
            normalized_text=build_normalized_text(dividend_raw_text),
            tickers_hint=["XYZ.N0000"],
            sectors_hint=["CONSUMER"],
            metadata={"scenario": "dividend", "priority": 2},
        )
    )

    retail_raw_text = (
        "COLOMBO - A small regional retailer opened one additional outlet in a provincial "
        "town and expects gradual footfall growth. The update did not indicate wider "
        "sector disruption or material market consequences."
    )
    documents.append(
        SourceDocument(
            document_id="retail-expansion-low-impact",
            source_type="NEWS",
            title="Regional retailer expands with one new outlet",
            url="https://example.invalid/regional-retail-expansion",
            published_at=datetime(2026, 5, 24, 9, 40, tzinfo=timezone.utc),
            retrieved_at=retrieved_at,
            raw_text=retail_raw_text,
            normalized_text=build_normalized_text(retail_raw_text),
            tickers_hint=[],
            sectors_hint=["RETAIL"],
            metadata={"scenario": "low_impact_local_business", "priority": 3},
        )
    )

    return documents


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("R10 local RAG smoke test requires DEEPSEEK_API_KEY to be set in the environment.")
        return 1

    try:
        store = LocalDocumentStore(RUNTIME_STORE_PATH)
        store.clear()
        store.append_many(_make_source_documents())

        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)

        query = DocumentQuery(
            keywords=["CBSL", "rate cut", "banking"],
            sectors=["BANKING"],
            limit=2,
        )
        analysis = analyzer.analyze(query)

        print("R10 Local RAG Smoke Test")
        print(f"Query: {query.model_dump(mode='json')}")
        print(analysis.model_dump_json(indent=2))
        return 0
    except (R10AnalysisError, ValueError) as error:
        print(f"R10 local RAG smoke test failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 local RAG smoke test failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
