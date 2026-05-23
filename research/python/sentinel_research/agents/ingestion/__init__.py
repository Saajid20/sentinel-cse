from sentinel_research.agents.ingestion.base import (
    DocumentSource,
    IngestionResult,
    ingest_documents,
)
from sentinel_research.agents.ingestion.static_source import StaticDocumentSource

__all__ = [
    "DocumentSource",
    "IngestionResult",
    "StaticDocumentSource",
    "ingest_documents",
]
