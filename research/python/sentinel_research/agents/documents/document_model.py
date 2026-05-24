from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sentinel_research.agents.schemas import SourceType


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_type: SourceType
    title: str
    url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime
    raw_text: str
    normalized_text: str | None = None
    tickers_hint: list[str] = Field(default_factory=list)
    sectors_hint: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("document_id", "title", "raw_text")
    @classmethod
    def _strip_required_str(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("url", "normalized_text", mode="before")
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("tickers_hint", "sectors_hint")
    @classmethod
    def _strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]
