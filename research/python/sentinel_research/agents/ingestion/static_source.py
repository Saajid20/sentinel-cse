from __future__ import annotations

from sentinel_research.agents.documents import SourceDocument
from sentinel_research.agents.ingestion.base import DocumentSource


class StaticDocumentSource(DocumentSource):
    def __init__(self, documents: list[SourceDocument], name: str = "static") -> None:
        self._documents = list(documents)
        self.name = name

    def fetch(self) -> list[SourceDocument]:
        return list(self._documents)
