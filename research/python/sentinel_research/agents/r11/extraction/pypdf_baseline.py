from __future__ import annotations

import importlib
from pathlib import Path

from sentinel_research.agents.r11.extraction.base import R11ExtractionError
from sentinel_research.agents.r11.schemas import (
    ExtractedFinancialTable,
    FinancialStatementType,
    R11ConfidenceLevel,
    SourceTrace,
)


def _import_pypdf_reader():
    try:
        return importlib.import_module("pypdf").PdfReader
    except ModuleNotFoundError as error:
        raise R11ExtractionError(
            "pypdf is required for R11 baseline PDF extraction. Install a compatible version from "
            "research/python/requirements.txt."
        ) from error


def _normalize_pdf_path(path: str | Path) -> Path:
    normalized = Path(path)
    if not normalized.exists():
        raise R11ExtractionError(f"PDF file does not exist: {normalized}")
    if normalized.suffix.lower() != ".pdf":
        raise R11ExtractionError(
            f"Unsupported file extension for R11 PDF extraction: {normalized.suffix or normalized.name}"
        )
    return normalized


def extract_text_lines_from_pdf(path: str | Path) -> dict[int, list[str]]:
    normalized_path = _normalize_pdf_path(path)
    reader_class = _import_pypdf_reader()

    try:
        with normalized_path.open("rb") as handle:
            reader = reader_class(handle)
            page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as error:
        raise R11ExtractionError(
            f"Failed to extract baseline PDF text from {normalized_path}: {error}"
        ) from error

    extracted: dict[int, list[str]] = {}
    for page_index, page_text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        extracted[page_index] = lines
    return extracted


class PypdfBaselineExtractor:
    def __init__(
        self,
        *,
        extraction_method: str = "pypdf_baseline",
        min_non_empty_lines: int = 2,
    ) -> None:
        if min_non_empty_lines < 1:
            raise ValueError("min_non_empty_lines must be >= 1")
        self._extraction_method = extraction_method
        self._min_non_empty_lines = min_non_empty_lines

    def extract(self, path: str | Path) -> list[ExtractedFinancialTable]:
        normalized_path = _normalize_pdf_path(path)
        page_lines = extract_text_lines_from_pdf(normalized_path)
        resolved_path = str(normalized_path.resolve())

        extracted_tables: list[ExtractedFinancialTable] = []
        for page_number, lines in page_lines.items():
            if len(lines) < self._min_non_empty_lines:
                continue

            extracted_tables.append(
                ExtractedFinancialTable(
                    table_id=f"pypdf_page_{page_number}",
                    statement_type=FinancialStatementType.UNKNOWN,
                    title=f"pypdf baseline page {page_number}",
                    page_number=page_number,
                    columns=["line_number", "text"],
                    rows=[
                        {
                            "line_number": line_number,
                            "text": line,
                        }
                        for line_number, line in enumerate(lines, start=1)
                    ],
                    extraction_method=self._extraction_method,
                    extraction_confidence=R11ConfidenceLevel.LOW,
                    source_trace=SourceTrace(
                        local_file_path=resolved_path,
                        page_number=page_number,
                        notes="pypdf baseline text extraction",
                    ),
                )
            )

        if not extracted_tables:
            raise R11ExtractionError(
                f"No extractable baseline table/text pages found in {normalized_path}"
            )

        return extracted_tables
