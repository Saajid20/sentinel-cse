from __future__ import annotations

import json

from sentinel_research.agents.core import ContextAgent
from sentinel_research.agents.documents import LocalDocumentStore
from sentinel_research.agents.retrieval import (
    DocumentQuery,
    RetrievalResult,
    SimpleDocumentRetriever,
)
from sentinel_research.agents.schemas import CseNewsAnalysis


class RetrievedContextAnalyzer:
    def __init__(self, store: LocalDocumentStore, agent: ContextAgent) -> None:
        self._store = store
        self._agent = agent

    def analyze(self, query: DocumentQuery) -> CseNewsAnalysis:
        documents = self._store.load_all()
        if not documents:
            raise ValueError("LocalDocumentStore contains no documents to analyze")

        retriever = SimpleDocumentRetriever(documents)
        results = retriever.search(query)
        if not results:
            raise ValueError("No documents matched the retrieval query")

        combined_text = self._build_combined_document(results)
        sources = self._build_sources(results)
        return self._agent.process_document(document=combined_text, sources=sources)

    @staticmethod
    def _build_combined_document(results: list[RetrievalResult]) -> str:
        blocks: list[str] = []
        for index, result in enumerate(results, start=1):
            document = result.document
            text = document.normalized_text or document.raw_text
            blocks.append(
                "\n".join(
                    [
                        f"--- DOCUMENT {index} ---",
                        f"document_id: {document.document_id}",
                        f"source_type: {document.source_type.value}",
                        f"title: {document.title}",
                        f"url: {document.url}",
                        f"published_at: {document.published_at.isoformat() if document.published_at else None}",
                        f"retrieved_at: {document.retrieved_at.isoformat()}",
                        f"score: {result.score}",
                        "matched_reasons: "
                        + json.dumps(result.matched_reasons, ensure_ascii=True),
                        "text:",
                        text,
                    ]
                )
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _build_sources(results: list[RetrievalResult]) -> list[dict]:
        sources: list[dict] = []
        for result in results:
            document = result.document
            sources.append(
                {
                    "source_type": document.source_type.value,
                    "title": document.title,
                    "url": document.url,
                    "published_at": document.published_at,
                    "retrieved_at": document.retrieved_at,
                }
            )
        return sources
