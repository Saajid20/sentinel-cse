from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sentinel_research.agents.r11.schemas import ExtractedFinancialTable


class R11ExtractionError(Exception):
    """Raised when local R11 extraction fails."""


class TableExtractor(Protocol):
    def extract(self, path: str | Path) -> list[ExtractedFinancialTable]:
        ...
