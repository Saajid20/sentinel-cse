from __future__ import annotations

import hashlib
import importlib.util
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sentinel_research.agents.documents import SourceDocument, build_normalized_text
from sentinel_research.agents.ingestion.base import DocumentSource
from sentinel_research.agents.schemas import SourceType

_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page\b")
_PDF_TJ_RE = re.compile(rb"\((?P<text>(?:\\.|[^\\)])*)\)\s*Tj")
_PDF_TJ_ARRAY_RE = re.compile(rb"\[(?P<items>.*?)\]\s*TJ", re.DOTALL)
_PDF_LITERAL_RE = re.compile(rb"\((?P<text>(?:\\.|[^\\)])*)\)")

_HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
if _HAS_PYPDF:
    from pypdf import PdfReader  # type: ignore[import-not-found]


class PdfExtractionError(Exception):
    """Raised when a local PDF file cannot be converted into a SourceDocument."""


@dataclass(slots=True)
class _PdfMetadata:
    source_type: SourceType
    title: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    tickers_hint: list[str] = field(default_factory=list)
    sectors_hint: list[str] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


def _read_pdf_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise PdfExtractionError(f"File does not appear to be a valid PDF: {path}")
    return data


def _decode_pdf_literal(value: bytes) -> str:
    chars: list[str] = []
    index = 0
    while index < len(value):
        byte = value[index]
        if byte != 0x5C:
            chars.append(chr(byte))
            index += 1
            continue

        index += 1
        if index >= len(value):
            chars.append("\\")
            break

        escaped = value[index]
        escape_map = {
            ord("n"): "\n",
            ord("r"): "\r",
            ord("t"): "\t",
            ord("b"): "\b",
            ord("f"): "\f",
            ord("("): "(",
            ord(")"): ")",
            ord("\\"): "\\",
        }
        if escaped in escape_map:
            chars.append(escape_map[escaped])
            index += 1
            continue

        if 48 <= escaped <= 55:
            octal_digits = bytes([escaped])
            index += 1
            for _ in range(2):
                if index < len(value) and 48 <= value[index] <= 55:
                    octal_digits += bytes([value[index]])
                    index += 1
                else:
                    break
            chars.append(chr(int(octal_digits, 8)))
            continue

        chars.append(chr(escaped))
        index += 1

    return "".join(chars)


def _extract_text_with_basic_parser(data: bytes) -> tuple[str, int | None]:
    text_parts: list[str] = []

    for match in _PDF_TJ_RE.finditer(data):
        text_parts.append(_decode_pdf_literal(match.group("text")))

    for match in _PDF_TJ_ARRAY_RE.finditer(data):
        items = match.group("items")
        for literal_match in _PDF_LITERAL_RE.finditer(items):
            text_parts.append(_decode_pdf_literal(literal_match.group("text")))

    page_count = len(_PDF_PAGE_RE.findall(data)) or None
    return "\n".join(part for part in text_parts if part.strip()), page_count


def _extract_pdf_text(path: Path) -> tuple[str, int | None]:
    data = _read_pdf_bytes(path)

    if _HAS_PYPDF:
        try:
            reader = PdfReader(path)
            page_texts = [page.extract_text() or "" for page in reader.pages]
        except Exception as error:  # pragma: no cover
            raise PdfExtractionError(f"Failed to extract PDF text from {path}: {error}") from error
        return "\n".join(text for text in page_texts if text.strip()), len(reader.pages)

    return _extract_text_with_basic_parser(data)


def _build_pdf_document(
    path: Path,
    *,
    source_type: SourceType,
    title: str | None,
    url: str | None,
    published_at: datetime | None,
    tickers_hint: list[str] | None,
    sectors_hint: list[str] | None,
    metadata: dict[str, str | int | float | bool | None] | None,
    now: Callable[[], datetime],
) -> SourceDocument:
    raw_text, page_count = _extract_pdf_text(path)
    if not raw_text.strip():
        raise PdfExtractionError(f"No extractable PDF text found in {path}")

    resolved_path = path.resolve()
    final_title = title.strip() if isinstance(title, str) and title.strip() else path.stem
    combined_metadata: dict[str, str | int | float | bool | None] = {
        "file_path": str(resolved_path),
        "file_name": path.name,
        "ingestion_source": "pdf_file",
    }
    if page_count is not None:
        combined_metadata["page_count"] = page_count
    if metadata:
        combined_metadata.update(metadata)

    document_id_input = f"{resolved_path}|{raw_text}"
    return SourceDocument(
        document_id="pdf_file:" + hashlib.sha256(document_id_input.encode("utf-8")).hexdigest()[:16],
        source_type=source_type,
        title=final_title,
        url=url,
        published_at=published_at,
        retrieved_at=now(),
        raw_text=raw_text,
        normalized_text=build_normalized_text(raw_text),
        tickers_hint=list(tickers_hint or []),
        sectors_hint=list(sectors_hint or []),
        metadata=combined_metadata,
    )


class PdfFileDocumentSource(DocumentSource):
    def __init__(
        self,
        path: str | Path,
        *,
        source_type: SourceType = SourceType.OTHER,
        title: str | None = None,
        url: str | None = None,
        published_at: datetime | None = None,
        tickers_hint: list[str] | None = None,
        sectors_hint: list[str] | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path)
        self._metadata = _PdfMetadata(
            source_type=source_type,
            title=title,
            url=url,
            published_at=published_at,
            tickers_hint=list(tickers_hint or []),
            sectors_hint=list(sectors_hint or []),
            metadata=dict(metadata or {}),
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.name = self._path.stem

    def fetch(self) -> list[SourceDocument]:
        if not self._path.exists():
            raise FileNotFoundError(self._path)
        if self._path.suffix.lower() != ".pdf":
            raise PdfExtractionError(
                f"Unsupported file extension for PDF ingestion: {self._path.suffix or self._path.name}"
            )

        return [
            _build_pdf_document(
                self._path,
                source_type=self._metadata.source_type,
                title=self._metadata.title,
                url=self._metadata.url,
                published_at=self._metadata.published_at,
                tickers_hint=self._metadata.tickers_hint,
                sectors_hint=self._metadata.sectors_hint,
                metadata=self._metadata.metadata,
                now=self._now,
            )
        ]


class DirectoryPdfDocumentSource(DocumentSource):
    def __init__(
        self,
        directory: str | Path,
        *,
        pattern: str = "*.pdf",
        source_type: SourceType = SourceType.OTHER,
        now: Callable[[], datetime] | None = None,
        default_tickers_hint: list[str] | None = None,
        default_sectors_hint: list[str] | None = None,
    ) -> None:
        self._directory = Path(directory)
        self._pattern = pattern
        self._source_type = source_type
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._default_tickers_hint = list(default_tickers_hint or [])
        self._default_sectors_hint = list(default_sectors_hint or [])
        self.name = self._directory.name or "pdf-directory"

    def fetch(self) -> list[SourceDocument]:
        if not self._directory.exists():
            raise FileNotFoundError(self._directory)

        documents: list[SourceDocument] = []
        for path in sorted(self._directory.glob(self._pattern)):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            try:
                documents.append(
                    _build_pdf_document(
                        path,
                        source_type=self._source_type,
                        title=None,
                        url=None,
                        published_at=None,
                        tickers_hint=self._default_tickers_hint,
                        sectors_hint=self._default_sectors_hint,
                        metadata=None,
                        now=self._now,
                    )
                )
            except PdfExtractionError as error:
                raise PdfExtractionError(f"{path}: {error}") from error
        return documents
