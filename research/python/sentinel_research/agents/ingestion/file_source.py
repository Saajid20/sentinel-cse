from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from sentinel_research.agents.documents import SourceDocument, build_normalized_text
from sentinel_research.agents.ingestion.base import DocumentSource
from sentinel_research.agents.schemas import SourceType

_SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm"}


class _VisibleTextHtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)


class ManualFileIngestionError(Exception):
    """Raised when a local file cannot be converted into a SourceDocument."""


@dataclass(slots=True)
class FileMetadata:
    source_type: SourceType
    title: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    tickers_hint: list[str] = field(default_factory=list)
    sectors_hint: list[str] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ManualFileIngestionError(f"Failed to decode UTF-8 file {path}: {error}") from error


def _extract_visible_html_text(text: str) -> str:
    parser = _VisibleTextHtmlExtractor()
    parser.feed(text)
    return " ".join(parser.text_parts).strip()


def _extract_text_from_file(path: Path) -> str:
    extension = path.suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise ManualFileIngestionError(f"Unsupported file extension for manual ingestion: {path.suffix or path.name}")

    text = _read_utf8_text(path)
    if extension in {".txt", ".md"}:
        return text
    return _extract_visible_html_text(text)


def _build_document_from_file(
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
    raw_text = _extract_text_from_file(path)
    if not raw_text.strip():
        raise ManualFileIngestionError(f"No usable text extracted from file {path}")

    resolved_path = path.resolve()
    final_title = title.strip() if isinstance(title, str) and title.strip() else path.stem
    combined_metadata: dict[str, str | int | float | bool | None] = {
        "file_path": str(resolved_path),
        "file_name": path.name,
        "ingestion_source": "manual_file",
    }
    if metadata:
        combined_metadata.update(metadata)

    document_id_input = f"{resolved_path}|{raw_text}"
    return SourceDocument(
        document_id="manual_file:" + hashlib.sha256(document_id_input.encode("utf-8")).hexdigest()[:16],
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


class TextFileDocumentSource(DocumentSource):
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
        self._metadata = FileMetadata(
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

        document = _build_document_from_file(
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
        return [document]


class DirectoryTextDocumentSource(DocumentSource):
    def __init__(
        self,
        directory: str | Path,
        *,
        pattern: str = "*",
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
        self.name = self._directory.name or "manual-file-directory"

    def fetch(self) -> list[SourceDocument]:
        if not self._directory.exists():
            raise FileNotFoundError(self._directory)

        documents: list[SourceDocument] = []
        for path in sorted(self._directory.glob(self._pattern)):
            if not path.is_file() or path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            documents.append(
                _build_document_from_file(
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
        return documents
