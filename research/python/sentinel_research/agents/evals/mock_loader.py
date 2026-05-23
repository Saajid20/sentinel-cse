from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class MockDocumentExpected(BaseModel):
    analysis_scope: Literal["MARKET", "SECTOR", "TICKER"]
    macro_risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    sentiment: Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
    signal_policy: Literal["SUPPORT", "BLOCK", "MANUAL_REVIEW", "NO_EFFECT"]
    must_include_catalyst_tags: list[str] = Field(default_factory=list)
    must_include_affected_sectors: list[str] = Field(default_factory=list)
    manual_review_required: bool


class MockDocumentCase(BaseModel):
    id: str
    title: str
    source_type: Literal["CBSL", "CSE_DISCLOSURE", "NEWS", "DAILY_FT", "OTHER"]
    url: str | None = None
    published_at: str | None = None
    document: str
    expected: MockDocumentExpected


def _default_mock_documents_path() -> Path:
    return Path(__file__).resolve().parent / "mock_documents" / "r10_mock_documents.jsonl"


def load_mock_documents(path: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_path = Path(path) if path is not None else _default_mock_documents_path()
    cases: list[dict[str, Any]] = []

    for line_number, raw_line in enumerate(
        resolved_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON in mock document file at line {line_number}: {error}"
            ) from error
        try:
            case = MockDocumentCase.model_validate(payload)
        except ValidationError as error:
            raise ValueError(
                f"Invalid mock document case at line {line_number}: {error}"
            ) from error
        cases.append(case.model_dump(mode="python"))

    return cases
