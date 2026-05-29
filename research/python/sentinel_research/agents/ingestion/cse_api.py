from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CSE_API_BASE_URL = "https://www.cse.lk/api"
_CSE_CDN_BASE_URL = "https://cdn.cse.lk"


class CseApiError(Exception):
    """Raised when a CSE API request or response fails validation."""


def normalize_cse_document_url(file_url: str) -> str:
    normalized = file_url.strip()
    if not normalized:
        raise ValueError("file_url must not be empty")
    if normalized.startswith(("http://", "https://")):
        return normalized
    if normalized.startswith("/cmt/"):
        return _CSE_CDN_BASE_URL + normalized
    if normalized.startswith("cmt/"):
        return _CSE_CDN_BASE_URL + "/" + normalized
    return normalized


class CseSecurity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str
    symbol: str
    active: int | bool | None = None

    @field_validator("name", "symbol")
    @classmethod
    def _strip_required_str(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class CseAnnouncementSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    announcement_id: int
    created_date_ms: int | None = None
    date_of_announcement: str | None = None
    announcement_category: str | None = None
    company: str | None = None
    symbol: str | None = None
    type: str | None = None
    remarks: str | None = None

    @field_validator(
        "date_of_announcement",
        "announcement_category",
        "company",
        "symbol",
        "type",
        "remarks",
        mode="before",
    )
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CseAnnouncementDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    file_name: str | None = None
    file_url: str
    file_size: int | None = None
    file_original_name: str | None = None
    content_type: str | None = None
    status: str | None = None
    full_url: str

    @field_validator(
        "file_name",
        "file_original_name",
        "content_type",
        "status",
        "full_url",
        mode="before",
    )
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("file_url")
    @classmethod
    def _strip_file_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("file_url must not be empty")
        return stripped

    @model_validator(mode="before")
    @classmethod
    def _populate_full_url(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        file_url = payload.get("file_url")
        if isinstance(file_url, str) and file_url.strip():
            payload["full_url"] = normalize_cse_document_url(file_url)
        return payload


class CseAnnouncementDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement_id: int
    title: str | None = None
    remarks: str | None = None
    date_of_announcement: str | None = None
    symbol: str | None = None
    company_name: str | None = None
    documents: list[CseAnnouncementDocument] = Field(default_factory=list)

    @field_validator("title", "remarks", "date_of_announcement", "symbol", "company_name", mode="before")
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CseFinancialReport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int | None = None
    path: str
    manual_date_ms: int | None = Field(default=None, alias="manualDate")
    uploaded_date: str | None = Field(default=None, alias="uploadedDate")
    file_text: str | None = Field(default=None, alias="fileText")
    name: str | None = None
    symbol: str | None = None
    logo_url: str | None = Field(default=None, alias="logoUrl")
    authorized_date: str | None = Field(default=None, alias="authorizedDate")
    full_url: str = Field(alias="fullUrl")

    @field_validator(
        "path",
        "uploaded_date",
        "file_text",
        "name",
        "symbol",
        "logo_url",
        "authorized_date",
        "full_url",
        mode="before",
    )
    @classmethod
    def _strip_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def _populate_full_url(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        path = payload.get("path")
        if isinstance(path, str) and path.strip():
            payload["fullUrl"] = normalize_cse_document_url(path)
        return payload


def _default_http_get(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    user_agent: str,
) -> object:
    request_headers = dict(headers)
    request_headers.setdefault("User-Agent", user_agent)
    request = urllib.request.Request(url, headers=request_headers)
    return urllib.request.urlopen(request, timeout=timeout)


def _default_http_post(
    url: str,
    *,
    data: bytes,
    headers: dict[str, str],
    timeout: float,
    user_agent: str,
) -> object:
    request_headers = dict(headers)
    request_headers.setdefault("User-Agent", user_agent)
    request = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
    return urllib.request.urlopen(request, timeout=timeout)


def _response_status(response: object) -> int:
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        code = getcode()
        if isinstance(code, int):
            return code
    return 200


def _decode_response_body(response: object) -> str:
    if hasattr(response, "read"):
        content = response.read()
    elif hasattr(response, "content"):
        content = getattr(response, "content")
    elif hasattr(response, "text"):
        return str(getattr(response, "text"))
    else:
        raise CseApiError("unsupported response object")

    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


class CseApiClient:
    def __init__(
        self,
        *,
        base_url: str = _CSE_API_BASE_URL,
        timeout: float = 20.0,
        user_agent: str = "Sentinel-CSE-R10/0.1",
        max_retries: int = 1,
        http_get: Callable[..., object] | None = None,
        http_post: Callable[..., object] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_retries = max_retries
        self._http_get = http_get or _default_http_get
        self._http_post = http_post or _default_http_post

    def list_securities(self) -> list[CseSecurity]:
        endpoint = "/allSecurityCode"
        payload = self._load_json("GET", endpoint)
        if not isinstance(payload, list):
            raise CseApiError(f"GET {endpoint} returned non-list JSON payload")
        try:
            return [CseSecurity.model_validate(item) for item in payload]
        except Exception as error:
            raise CseApiError(f"GET {endpoint} returned invalid security payload: {error}") from error

    def get_announcements_by_company(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> list[CseAnnouncementSummary]:
        normalized_symbol = symbol.strip()
        normalized_from_date = from_date.strip()
        normalized_to_date = to_date.strip()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        if not normalized_from_date:
            raise ValueError("from_date must not be empty")
        if not normalized_to_date:
            raise ValueError("to_date must not be empty")

        endpoint = "/getAnnouncementByCompany"
        payload = self._load_json(
            "POST",
            endpoint,
            form_payload={
                "symbol": normalized_symbol,
                "fromDate": normalized_from_date,
                "toDate": normalized_to_date,
            },
        )
        if not isinstance(payload, dict):
            raise CseApiError(
                f"POST {endpoint} for symbol={normalized_symbol} returned non-object JSON payload"
            )
        summaries = payload.get("reqCompanyAnnouncement")
        if not isinstance(summaries, list):
            raise CseApiError(
                f"POST {endpoint} for symbol={normalized_symbol} missing reqCompanyAnnouncement list"
            )
        try:
            return [
                CseAnnouncementSummary.model_validate(
                    {
                        "id": item.get("id"),
                        "announcement_id": item.get("announcementId"),
                        "created_date_ms": item.get("createdDate"),
                        "date_of_announcement": item.get("dateOfAnnouncement"),
                        "announcement_category": item.get("announcementCategory"),
                        "company": item.get("company"),
                        "symbol": item.get("symbol"),
                        "type": item.get("type"),
                        "remarks": item.get("remarks"),
                    }
                )
                for item in summaries
            ]
        except Exception as error:
            raise CseApiError(
                f"POST {endpoint} for symbol={normalized_symbol} returned invalid announcement summary payload: {error}"
            ) from error

    def get_announcement_detail(self, announcement_id: int) -> CseAnnouncementDetail:
        endpoint = "/getGeneralAnnouncementById"
        payload = self._load_json(
            "POST",
            endpoint,
            form_payload={"announcementId": str(announcement_id)},
        )
        if not isinstance(payload, dict):
            raise CseApiError(
                f"POST {endpoint} for announcement_id={announcement_id} returned non-object JSON payload"
            )
        base_announcement = payload.get("reqBaseAnnouncement")
        documents = payload.get("reqAnnouncementDocs")
        if not isinstance(base_announcement, dict):
            raise CseApiError(
                f"POST {endpoint} for announcement_id={announcement_id} missing reqBaseAnnouncement object"
            )
        if not isinstance(documents, list):
            raise CseApiError(
                f"POST {endpoint} for announcement_id={announcement_id} missing reqAnnouncementDocs list"
            )
        try:
            return CseAnnouncementDetail.model_validate(
                {
                    "announcement_id": base_announcement.get("id")
                    or base_announcement.get("announcementId")
                    or announcement_id,
                    "title": base_announcement.get("title"),
                    "remarks": base_announcement.get("remarks"),
                    "date_of_announcement": base_announcement.get("dateOfAnnouncement"),
                    "symbol": base_announcement.get("symbol"),
                    "company_name": base_announcement.get("companyName"),
                    "documents": [
                        {
                            "id": item.get("id"),
                            "file_name": item.get("fileName"),
                            "file_url": item.get("fileUrl"),
                            "file_size": item.get("fileSize"),
                            "file_original_name": item.get("fileOriginalName"),
                            "content_type": item.get("contentType"),
                            "status": item.get("status"),
                        }
                        for item in documents
                    ],
                }
            )
        except Exception as error:
            raise CseApiError(
                f"POST {endpoint} for announcement_id={announcement_id} returned invalid announcement detail payload: {error}"
            ) from error

    def get_financial_reports(self) -> list[CseFinancialReport]:
        endpoint = "/getFinancialAnnouncement"
        payload = self._load_json(
            "POST",
            endpoint,
            form_payload={},
        )
        if not isinstance(payload, dict):
            raise CseApiError(f"POST {endpoint} returned non-object JSON payload")
        reports = payload.get("reqFinancialAnnouncemnets")
        if not isinstance(reports, list):
            raise CseApiError(
                f"POST {endpoint} missing reqFinancialAnnouncemnets list"
            )
        try:
            return [CseFinancialReport.model_validate(item) for item in reports]
        except Exception as error:
            raise CseApiError(
                f"POST {endpoint} returned invalid financial report payload: {error}"
            ) from error

    def _load_json(
        self,
        method: str,
        endpoint: str,
        *,
        form_payload: dict[str, str] | None = None,
    ) -> object:
        url = self._base_url + endpoint
        headers = self._build_headers(method)
        try:
            if method == "GET":
                response = self._request_with_retries(
                    self._http_get,
                    method=method,
                    endpoint=endpoint,
                    url=url,
                    headers=headers,
                )
            else:
                encoded_payload = urllib.parse.urlencode(form_payload or {}).encode("utf-8")
                response = self._request_with_retries(
                    self._http_post,
                    method=method,
                    endpoint=endpoint,
                    url=url,
                    headers=headers,
                    data=encoded_payload,
                )
        except urllib.error.HTTPError as error:
            raise CseApiError(f"{method} {endpoint} returned HTTP {error.code}") from error

        status = _response_status(response)
        if status != 200:
            raise CseApiError(f"{method} {endpoint} returned HTTP {status}")

        try:
            return json.loads(_decode_response_body(response))
        except json.JSONDecodeError as error:
            raise CseApiError(f"{method} {endpoint} returned invalid JSON: {error}") from error

    def _build_headers(self, method: str) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.cse.lk",
            "Referer": "https://www.cse.lk/",
            "Connection": "close",
        }
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return headers

    def _request_with_retries(
        self,
        request_fn: Callable[..., object],
        *,
        method: str,
        endpoint: str,
        url: str,
        headers: dict[str, str],
        data: bytes | None = None,
    ) -> object:
        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt_index in range(attempts):
            try:
                request_kwargs = {
                    "headers": headers,
                    "timeout": self._timeout,
                    "user_agent": self._user_agent,
                }
                if data is not None:
                    request_kwargs["data"] = data
                return request_fn(url, **request_kwargs)
            except urllib.error.HTTPError:
                raise
            except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionResetError) as error:
                last_error = error
                if attempt_index >= self._max_retries:
                    break

        raise CseApiError(
            f"{method} {endpoint} request failed after {attempts} attempt(s): {last_error}"
        ) from last_error
