from __future__ import annotations

import hashlib
import re
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable, Any

from sentinel_research.agents.documents import SourceDocument, build_normalized_text
from sentinel_research.agents.ingestion.base import DocumentSource
from sentinel_research.agents.schemas import SourceType

_META_PUBLISHED_PATTERNS = (
    re.compile(
        r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|publishdate|date|dc\.date|dc\.date\.issued)["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
)


class _CbslHtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._tag_stack: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        self._tag_stack.append(normalized_tag)
        if normalized_tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._tag_stack:
            self._tag_stack.pop()
        if normalized_tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if current_tag == "title":
            self.title_parts.append(text)
            return
        if current_tag == "h1":
            self.h1_parts.append(text)
        self.text_parts.append(text)


class CbslFetchError(Exception):
    """Raised when a CBSL URL cannot be fetched or converted into a SourceDocument."""


def _default_http_get(url: str, *, timeout: float, user_agent: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    return urllib.request.urlopen(request, timeout=timeout)


def _extract_published_at(html: str) -> datetime | None:
    for pattern in _META_PUBLISHED_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        raw_value = match.group(1).strip()
        try:
            normalized = raw_value.replace("Z", "+00:00")
            published_at = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        return published_at
    return None


def _extract_html_content(html: str) -> tuple[str, str]:
    parser = _CbslHtmlExtractor()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip() or " ".join(parser.h1_parts).strip() or "CBSL document"
    raw_text = " ".join(parser.text_parts).strip()
    return title, raw_text


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _response_content_type(response: object) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is not None:
        get_content_type = getattr(headers, "get_content_type", None)
        if callable(get_content_type):
            return str(get_content_type()).lower()
        get = getattr(headers, "get", None)
        if callable(get):
            value = get("Content-Type")
            if value is not None:
                return str(value).lower()
    content_type = getattr(response, "content_type", None)
    if content_type is not None:
        return str(content_type).lower()
    return None


class CbslUrlDocumentSource(DocumentSource):
    def __init__(
        self,
        urls: list[str],
        *,
        timeout: float = 20.0,
        user_agent: str = "Sentinel-CSE-R10/0.1",
        now: Callable[[], datetime] | None = None,
        http_get: Callable[..., object] | None = None,
    ) -> None:
        normalized_urls = [url.strip() for url in urls if url.strip()]
        if not normalized_urls:
            raise ValueError("urls must contain at least one non-empty URL")
        self._urls = normalized_urls
        self._timeout = timeout
        self._user_agent = user_agent
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._http_get = http_get or _default_http_get
        self.name = "cbsl-url"

    def fetch(self) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        for url in self._urls:
            documents.append(self._fetch_one(url))
        return documents

    def _fetch_one(self, url: str) -> SourceDocument:
        if _is_pdf_url(url):
            raise CbslFetchError(f"PDF extraction is not supported yet for CBSL URL: {url}")

        try:
            response = self._http_get(
                url,
                timeout=self._timeout,
                user_agent=self._user_agent,
            )
        except Exception as error:
            raise CbslFetchError(f"Failed to fetch CBSL URL {url}: {error}") from error

        status = getattr(response, "status", getattr(response, "status_code", 200))
        if status != 200:
            raise CbslFetchError(f"Failed to fetch CBSL URL {url}: HTTP {status}")
        content_type = _response_content_type(response)
        if content_type is not None and "application/pdf" in content_type:
            raise CbslFetchError(f"PDF extraction is not supported yet for CBSL URL: {url}")

        html = self._decode_response_content(response, url)
        title, raw_text = _extract_html_content(html)
        if not raw_text:
            raise CbslFetchError(f"Failed to extract usable text from CBSL URL {url}")

        return SourceDocument(
            document_id="cbsl:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
            source_type=SourceType.CBSL,
            title=title,
            url=url,
            published_at=_extract_published_at(html),
            retrieved_at=self._now(),
            raw_text=raw_text,
            normalized_text=build_normalized_text(raw_text),
            tickers_hint=[],
            sectors_hint=[],
            metadata={"source": "CBSL", "fetch_url": url},
        )

    @staticmethod
    def _decode_response_content(response: object, url: str) -> str:
        if hasattr(response, "read"):
            content = response.read()
        elif hasattr(response, "content"):
            content = getattr(response, "content")
        elif hasattr(response, "text"):
            return str(getattr(response, "text"))
        else:
            raise CbslFetchError(f"Failed to read CBSL URL {url}: unsupported response object")

        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return str(content)
