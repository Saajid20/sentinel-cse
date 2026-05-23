from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, model_validator, field_validator

from sentinel_research.agents.documents import LocalDocumentStore, SourceDocument


class DocumentSource(ABC):
    @abstractmethod
    def fetch(self) -> list[SourceDocument]:
        """Return locally prepared SourceDocument objects."""


class IngestionResult(BaseModel):
    source_name: str
    fetched_count: int = Field(ge=0)
    stored_count: int = Field(ge=0)
    skipped_count: int = Field(default=0, ge=0)
    document_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @field_validator("source_name")
    @classmethod
    def _strip_source_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source_name must not be empty")
        return stripped

    @field_validator("document_ids", "errors")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def _validate_counts(self) -> "IngestionResult":
        if self.stored_count > self.fetched_count:
            raise ValueError("stored_count cannot exceed fetched_count")
        if self.skipped_count > self.fetched_count:
            raise ValueError("skipped_count cannot exceed fetched_count")
        return self


def ingest_documents(
    source: DocumentSource,
    store: LocalDocumentStore,
    source_name: str | None = None,
) -> IngestionResult:
    resolved_source_name = source_name or getattr(source, "name", type(source).__name__)

    try:
        fetched_documents = source.fetch()
    except Exception as error:
        return IngestionResult(
            source_name=resolved_source_name,
            fetched_count=0,
            stored_count=0,
            skipped_count=0,
            errors=[str(error)],
        )

    if not isinstance(fetched_documents, list):
        return IngestionResult(
            source_name=resolved_source_name,
            fetched_count=0,
            stored_count=0,
            skipped_count=0,
            errors=["source.fetch() must return a list of SourceDocument objects"],
        )

    invalid_items = [
        index for index, item in enumerate(fetched_documents, start=1)
        if not isinstance(item, SourceDocument)
    ]
    if invalid_items:
        return IngestionResult(
            source_name=resolved_source_name,
            fetched_count=len(fetched_documents),
            stored_count=0,
            skipped_count=0,
            errors=[
                "source.fetch() returned non-SourceDocument items at positions "
                + ", ".join(str(index) for index in invalid_items)
            ],
        )

    if not fetched_documents:
        return IngestionResult(
            source_name=resolved_source_name,
            fetched_count=0,
            stored_count=0,
            skipped_count=0,
        )

    store.append_many(fetched_documents)
    return IngestionResult(
        source_name=resolved_source_name,
        fetched_count=len(fetched_documents),
        stored_count=len(fetched_documents),
        skipped_count=0,
        document_ids=[document.document_id for document in fetched_documents],
    )
