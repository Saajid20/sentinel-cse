from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from sentinel_research.agents.documents import SourceDocument
from sentinel_research.agents.schemas import SourceType


class DocumentQuery(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    source_types: list[SourceType] = Field(default_factory=list)
    published_after: datetime | None = None
    published_before: datetime | None = None
    retrieved_after: datetime | None = None
    retrieved_before: datetime | None = None
    limit: int = 10

    @field_validator("keywords", "tickers", "sectors")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("limit")
    @classmethod
    def _validate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit must be greater than 0")
        return value


class RetrievalResult(BaseModel):
    document: SourceDocument
    score: float
    matched_reasons: list[str] = Field(default_factory=list)


class SimpleDocumentRetriever:
    def __init__(self, documents: list[SourceDocument]) -> None:
        self._documents = list(documents)

    def search(self, query: DocumentQuery) -> list[RetrievalResult]:
        if not self._has_filters(query):
            ordered_documents = sorted(
                self._documents,
                key=lambda document: document.retrieved_at,
                reverse=True,
            )
            return [
                RetrievalResult(document=document, score=0.0, matched_reasons=[])
                for document in ordered_documents[: query.limit]
            ]

        results: list[RetrievalResult] = []
        for document in self._documents:
            if not self._matches_date_filters(document, query):
                continue
            if query.source_types and document.source_type not in query.source_types:
                continue

            score = 0.0
            meaningful_match = False
            matched_reasons: list[str] = []
            searchable_text = self._build_searchable_text(document)

            for keyword in query.keywords:
                if keyword.lower() in searchable_text:
                    score += 1.0
                    meaningful_match = True
                    matched_reasons.append(f"keyword:{keyword}")

            for ticker in query.tickers:
                if self._matches_exact_or_text(
                    ticker,
                    document.tickers_hint,
                    searchable_text,
                ):
                    score += 2.0
                    meaningful_match = True
                    matched_reasons.append(f"ticker:{ticker}")

            for sector in query.sectors:
                if self._matches_exact_or_text(
                    sector,
                    document.sectors_hint,
                    searchable_text,
                ):
                    score += 1.5
                    meaningful_match = True
                    matched_reasons.append(f"sector:{sector}")

            if query.source_types:
                score += 0.25
                if query.keywords or query.tickers or query.sectors:
                    matched_reasons.append(f"source_type:{document.source_type.value}")

            if not self._should_include_document(query, score, meaningful_match):
                continue

            if self._is_source_type_or_date_only_query(query):
                matched_reasons = []

            results.append(
                RetrievalResult(
                    document=document,
                    score=score,
                    matched_reasons=matched_reasons,
                )
            )

        results.sort(
            key=lambda result: (result.score, result.document.retrieved_at),
            reverse=True,
        )
        return results[: query.limit]

    @staticmethod
    def _has_filters(query: DocumentQuery) -> bool:
        return any(
            (
                query.keywords,
                query.tickers,
                query.sectors,
                query.source_types,
                query.published_after is not None,
                query.published_before is not None,
                query.retrieved_after is not None,
                query.retrieved_before is not None,
            )
        )

    @staticmethod
    def _is_source_type_or_date_only_query(query: DocumentQuery) -> bool:
        return not (query.keywords or query.tickers or query.sectors)

    @staticmethod
    def _matches_date_filters(document: SourceDocument, query: DocumentQuery) -> bool:
        if query.published_after is not None:
            if document.published_at is None or document.published_at <= query.published_after:
                return False
        if query.published_before is not None:
            if document.published_at is None or document.published_at >= query.published_before:
                return False
        if query.retrieved_after is not None and document.retrieved_at <= query.retrieved_after:
            return False
        if query.retrieved_before is not None and document.retrieved_at >= query.retrieved_before:
            return False
        return True

    @staticmethod
    def _build_searchable_text(document: SourceDocument) -> str:
        parts = [
            document.title,
            document.raw_text,
            document.normalized_text or "",
            " ".join(document.tickers_hint),
            " ".join(document.sectors_hint),
        ]
        return " ".join(parts).lower()

    @staticmethod
    def _matches_exact_or_text(
        value: str,
        hints: list[str],
        searchable_text: str,
    ) -> bool:
        normalized_value = value.lower()
        return any(hint.lower() == normalized_value for hint in hints) or normalized_value in searchable_text

    @staticmethod
    def _should_include_document(
        query: DocumentQuery,
        score: float,
        meaningful_match: bool,
    ) -> bool:
        if query.keywords or query.tickers or query.sectors:
            return meaningful_match
        if query.source_types:
            return score > 0.0
        return True
