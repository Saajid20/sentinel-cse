from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.ingestion import (  # noqa: E402
    CseApiClient,
    CseApiError,
    CseFinancialReport,
    normalize_cse_document_url,
)


class FakeResponse:
    def __init__(self, body: str, *, status: int = 200) -> None:
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body


def make_client(
    *,
    max_retries: int = 1,
    http_get=None,
    http_post=None,
) -> CseApiClient:
    return CseApiClient(
        max_retries=max_retries,
        http_get=http_get,
        http_post=http_post,
    )


def test_normalize_cse_document_url_handles_cmt_prefix() -> None:
    result = normalize_cse_document_url("cmt/announcement_portal_prod/foo.pdf")

    assert result == "https://cdn.cse.lk/cmt/announcement_portal_prod/foo.pdf"


def test_normalize_cse_document_url_handles_leading_slash_cmt_prefix() -> None:
    result = normalize_cse_document_url("/cmt/announcement_portal_prod/foo.pdf")

    assert result == "https://cdn.cse.lk/cmt/announcement_portal_prod/foo.pdf"


def test_normalize_cse_document_url_preserves_full_https_url() -> None:
    result = normalize_cse_document_url("https://cdn.cse.lk/cmt/foo.pdf")

    assert result == "https://cdn.cse.lk/cmt/foo.pdf"


def test_list_securities_parses_sample_response() -> None:
    calls: list[dict[str, object]] = []

    def fake_http_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            json.dumps(
                [
                    {
                        "id": 297,
                        "name": " JOHN KEELLS HOLDINGS PLC ",
                        "symbol": " JKH.N0000 ",
                        "active": 1,
                    }
                ]
            )
        )

    securities = make_client(http_get=fake_http_get).list_securities()

    assert len(securities) == 1
    assert securities[0].id == 297
    assert securities[0].name == "JOHN KEELLS HOLDINGS PLC"
    assert securities[0].symbol == "JKH.N0000"
    assert calls == [
        {
            "url": "https://www.cse.lk/api/allSecurityCode",
            "headers": {
                "User-Agent": "Sentinel-CSE-R10/0.1",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.cse.lk",
                "Referer": "https://www.cse.lk/",
                "Connection": "close",
            },
            "timeout": 20.0,
            "user_agent": "Sentinel-CSE-R10/0.1",
        }
    ]


def test_get_announcements_by_company_sends_symbol_and_date_window_and_parses_one_announcement() -> None:
    calls: list[dict[str, object]] = []

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            json.dumps(
                {
                    "reqCompanyAnnouncement": [
                        {
                            "id": 19694,
                            "announcementId": 23051,
                            "createdDate": 1707383790000,
                            "dateOfAnnouncement": " 08 Feb 2024 ",
                            "announcementCategory": " CORPORATE DISCLOSURE ",
                            "company": " JOHN KEELLS HOLDINGS PLC ",
                            "symbol": " JKH.N0000 ",
                            "type": " new ",
                            "remarks": " sample remark ",
                        }
                    ]
                }
            )
        )

    summaries = make_client(http_post=fake_http_post).get_announcements_by_company(
        "JKH.N0000",
        "2024-02-08",
        "2024-02-08",
    )

    assert len(summaries) == 1
    assert summaries[0].announcement_id == 23051
    assert summaries[0].created_date_ms == 1707383790000
    assert summaries[0].date_of_announcement == "08 Feb 2024"
    assert summaries[0].announcement_category == "CORPORATE DISCLOSURE"
    assert summaries[0].company == "JOHN KEELLS HOLDINGS PLC"
    assert summaries[0].symbol == "JKH.N0000"
    assert summaries[0].type == "new"
    assert summaries[0].remarks == "sample remark"
    assert calls == [
        {
            "url": "https://www.cse.lk/api/getAnnouncementByCompany",
            "data": b"symbol=JKH.N0000&fromDate=2024-02-08&toDate=2024-02-08",
            "headers": {
                "User-Agent": "Sentinel-CSE-R10/0.1",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.cse.lk",
                "Referer": "https://www.cse.lk/",
                "Connection": "close",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            "timeout": 20.0,
            "user_agent": "Sentinel-CSE-R10/0.1",
        }
    ]


def test_post_sends_origin_and_referer_headers() -> None:
    captured_headers: list[dict[str, str]] = []

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        captured_headers.append(kwargs["headers"])
        return FakeResponse(json.dumps({"reqCompanyAnnouncement": []}))

    make_client(http_post=fake_http_post).get_announcements_by_company(
        "JKH.N0000",
        "2024-02-08",
        "2024-02-08",
    )

    assert captured_headers == [
        {
            "User-Agent": "Sentinel-CSE-R10/0.1",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.cse.lk",
            "Referer": "https://www.cse.lk/",
            "Connection": "close",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
    ]


def test_transient_url_error_retries_once_and_then_succeeds() -> None:
    attempts = 0

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.URLError("temporary ssl eof")
        return FakeResponse(json.dumps({"reqCompanyAnnouncement": []}))

    result = make_client(max_retries=1, http_post=fake_http_post).get_announcements_by_company(
        "JKH.N0000",
        "2024-02-08",
        "2024-02-08",
    )

    assert result == []
    assert attempts == 2


def test_transient_url_error_after_retries_raises_cse_api_error_with_attempt_count() -> None:
    attempts = 0

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise urllib.error.URLError("temporary ssl eof")

    client = make_client(max_retries=1, http_post=fake_http_post)

    with pytest.raises(
        CseApiError,
        match=r"POST /getAnnouncementByCompany request failed after 2 attempt\(s\):",
    ):
        client.get_announcements_by_company("JKH.N0000", "2024-02-08", "2024-02-08")

    assert attempts == 2


def test_get_announcements_by_company_returns_empty_list_for_empty_response() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(json.dumps({"reqCompanyAnnouncement": []}))

    summaries = make_client(http_post=fake_http_post).get_announcements_by_company(
        "JKH.N0000",
        "2024-02-08",
        "2024-02-08",
    )

    assert summaries == []


def test_get_announcement_detail_parses_base_announcement_and_documents() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(
            json.dumps(
                {
                    "reqBaseAnnouncement": {
                        "id": 23051,
                        "title": " CORPORATE DISCLOSURE ",
                        "remarks": " DISCLOSURE UNDER RULE 36 ",
                        "dateOfAnnouncement": " 08 Feb 2024 ",
                        "symbol": " JKH ",
                        "companyName": " JOHN KEELLS HOLDINGS PLC ",
                    },
                    "reqAnnouncementDocs": [
                        {
                            "id": 149892,
                            "fileName": " doc.pdf ",
                            "fileUrl": "cmt/announcement_portal_prod/doc.pdf",
                            "fileSize": 101844,
                            "fileOriginalName": " original.pdf ",
                            "contentType": " application/pdf ",
                            "status": " 1 ",
                        }
                    ],
                }
            )
        )

    detail = make_client(http_post=fake_http_post).get_announcement_detail(23051)

    assert detail.announcement_id == 23051
    assert detail.title == "CORPORATE DISCLOSURE"
    assert detail.remarks == "DISCLOSURE UNDER RULE 36"
    assert detail.date_of_announcement == "08 Feb 2024"
    assert detail.symbol == "JKH"
    assert detail.company_name == "JOHN KEELLS HOLDINGS PLC"
    assert len(detail.documents) == 1
    assert detail.documents[0].file_name == "doc.pdf"
    assert detail.documents[0].file_url == "cmt/announcement_portal_prod/doc.pdf"


def test_get_financial_reports_parses_response_and_normalizes_full_url() -> None:
    calls: list[dict[str, object]] = []

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            json.dumps(
                {
                    "reqFinancialAnnouncemnets": [
                        {
                            "id": 51415,
                            "path": "cmt/upload_report_file/446_1779883742342.03.2026 Consolidated Interim Financial Statements.pdf",
                            "manualDate": 1774895400000,
                            "uploadedDate": "27 May 2026 05:39:02 PM",
                            "fileText": "Interim Financial Statements for the Quarter ended 31st March 2026",
                            "name": "DIALOG AXIATA PLC",
                            "symbol": "DIAL",
                            "logoUrl": "upload_logo/446_1192516470.gif",
                            "authorizedDate": "27 May 2026 06:11:25 PM",
                        }
                    ]
                }
            )
        )

    reports = make_client(http_post=fake_http_post).get_financial_reports()

    assert len(reports) == 1
    assert isinstance(reports[0], CseFinancialReport)
    assert reports[0].id == 51415
    assert reports[0].path == "cmt/upload_report_file/446_1779883742342.03.2026 Consolidated Interim Financial Statements.pdf"
    assert reports[0].manual_date_ms == 1774895400000
    assert reports[0].uploaded_date == "27 May 2026 05:39:02 PM"
    assert reports[0].file_text == "Interim Financial Statements for the Quarter ended 31st March 2026"
    assert reports[0].name == "DIALOG AXIATA PLC"
    assert reports[0].symbol == "DIAL"
    assert reports[0].logo_url == "upload_logo/446_1192516470.gif"
    assert reports[0].authorized_date == "27 May 2026 06:11:25 PM"
    assert reports[0].full_url == (
        "https://cdn.cse.lk/cmt/upload_report_file/"
        "446_1779883742342.03.2026 Consolidated Interim Financial Statements.pdf"
    )
    assert calls == [
        {
            "url": "https://www.cse.lk/api/getFinancialAnnouncement",
            "data": b"",
            "headers": {
                "User-Agent": "Sentinel-CSE-R10/0.1",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.cse.lk",
                "Referer": "https://www.cse.lk/",
                "Connection": "close",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            "timeout": 20.0,
            "user_agent": "Sentinel-CSE-R10/0.1",
        }
    ]


def test_get_financial_reports_returns_empty_list_for_empty_response() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(json.dumps({"reqFinancialAnnouncemnets": []}))

    reports = make_client(http_post=fake_http_post).get_financial_reports()

    assert reports == []


def test_get_financial_reports_missing_expected_key_raises_cse_api_error() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(json.dumps({"wrongKey": []}))

    client = make_client(http_post=fake_http_post)

    with pytest.raises(
        CseApiError,
        match="missing reqFinancialAnnouncemnets list",
    ):
        client.get_financial_reports()


def test_detail_document_full_url_is_normalized_correctly() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(
            json.dumps(
                {
                    "reqBaseAnnouncement": {"id": 23051},
                    "reqAnnouncementDocs": [
                        {
                            "fileUrl": "/cmt/announcement_portal_prod/foo.pdf",
                        }
                    ],
                }
            )
        )

    detail = make_client(http_post=fake_http_post).get_announcement_detail(23051)

    assert detail.documents[0].full_url == "https://cdn.cse.lk/cmt/announcement_portal_prod/foo.pdf"


def test_inconsistent_symbol_handling_does_not_crash() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        if url.endswith("/getAnnouncementByCompany"):
            return FakeResponse(
                json.dumps(
                    {
                        "reqCompanyAnnouncement": [
                            {
                                "announcementId": 23051,
                                "company": "JOHN KEELLS HOLDINGS PLC",
                                "symbol": "JKH.N0000",
                            }
                        ]
                    }
                )
            )
        return FakeResponse(
            json.dumps(
                {
                    "reqBaseAnnouncement": {
                        "id": 23051,
                        "symbol": "JKH",
                    },
                    "reqAnnouncementDocs": [],
                }
            )
        )

    client = make_client(http_post=fake_http_post)
    summaries = client.get_announcements_by_company("JKH.N0000", "2024-02-08", "2024-02-08")
    detail = client.get_announcement_detail(23051)

    assert summaries[0].symbol == "JKH.N0000"
    assert detail.symbol == "JKH"


def test_non_200_fake_response_raises_cse_api_error() -> None:
    def fake_http_get(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse("{}", status=500)

    client = make_client(http_get=fake_http_get)

    with pytest.raises(CseApiError, match="GET /allSecurityCode returned HTTP 500"):
        client.list_securities()


def test_invalid_json_fake_response_raises_cse_api_error() -> None:
    def fake_http_get(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse("{not-json")

    client = make_client(http_get=fake_http_get)

    with pytest.raises(CseApiError, match="GET /allSecurityCode returned invalid JSON"):
        client.list_securities()


def test_missing_expected_keys_raise_cse_api_error() -> None:
    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(json.dumps({"wrongKey": []}))

    client = make_client(http_post=fake_http_post)

    with pytest.raises(
        CseApiError,
        match="missing reqCompanyAnnouncement list",
    ):
        client.get_announcements_by_company("JKH.N0000", "2024-02-08", "2024-02-08")


def test_no_test_calls_real_network() -> None:
    http_get_calls = 0
    http_post_calls = 0

    def fake_http_get(url: str, **kwargs: object) -> FakeResponse:
        nonlocal http_get_calls
        http_get_calls += 1
        return FakeResponse(json.dumps([]))

    def fake_http_post(url: str, **kwargs: object) -> FakeResponse:
        nonlocal http_post_calls
        http_post_calls += 1
        if url.endswith("/getFinancialAnnouncement"):
            return FakeResponse(json.dumps({"reqFinancialAnnouncemnets": []}))
        return FakeResponse(json.dumps({"reqCompanyAnnouncement": []}))

    client = make_client(http_get=fake_http_get, http_post=fake_http_post)
    client.list_securities()
    client.get_announcements_by_company("JKH.N0000", "2024-02-08", "2024-02-08")
    client.get_financial_reports()

    assert http_get_calls == 1
    assert http_post_calls == 2


def test_no_test_calls_deepseek() -> None:
    source = (PYTHON_ROOT / "sentinel_research" / "agents" / "ingestion" / "cse_api.py").read_text(
        encoding="utf-8"
    )

    assert "DeepSeek" not in source
    assert "DEEPSEEK" not in source
