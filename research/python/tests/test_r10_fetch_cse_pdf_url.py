from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import pdf_source as pdf_source_module  # noqa: E402

SCRIPT_PATH = PYTHON_ROOT / "scripts" / "r10_fetch_cse_pdf_url.py"


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-fetch-cse-pdf-url-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


@pytest.fixture
def script_module():
    spec = importlib.util.spec_from_file_location("r10_fetch_cse_pdf_url", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _make_fake_pdf_reader(
    *,
    page_texts_by_name: dict[str, list[str]] | None = None,
):
    class FakePdfReader:
        def __init__(self, handle) -> None:
            texts = (page_texts_by_name or {}).get(Path(handle.name).name, [Path(handle.name).stem])
            self.pages = [_FakePdfPage(text) for text in texts]

    return FakePdfReader


@pytest.fixture
def patch_pypdf_reader(monkeypatch):
    def _patch(*, page_texts_by_name: dict[str, list[str]] | None = None) -> None:
        monkeypatch.setattr(
            pdf_source_module,
            "_import_pypdf_reader",
            lambda: _make_fake_pdf_reader(page_texts_by_name=page_texts_by_name),
        )

    return _patch


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_pdf(path: Path, text: str) -> None:
    content_stream = f"BT\n/F1 12 Tf\n72 720 Td\n({_pdf_escape(text)}) Tj\nET\n".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            b"5 0 obj\n<< /Length "
            + str(len(content_stream)).encode("ascii")
            + b" >>\nstream\n"
            + content_stream
            + b"endstream\nendobj\n"
        ),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    startxref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{startxref}\n%%EOF"
        ).encode("ascii")
    )
    path.write_bytes(bytes(pdf))


def test_validate_cse_pdf_url_requires_https(script_module) -> None:
    with pytest.raises(ValueError, match="must use https"):
        script_module._validate_cse_pdf_url("http://cdn.cse.lk/cmt/upload_report_file/report.pdf")


def test_validate_cse_pdf_url_requires_cse_cdn_pdf_path(script_module) -> None:
    with pytest.raises(ValueError, match="must point to cdn.cse.lk"):
        script_module._validate_cse_pdf_url("https://example.com/report.pdf")

    with pytest.raises(ValueError, match=r"must end with \.pdf"):
        script_module._validate_cse_pdf_url("https://cdn.cse.lk/cmt/upload_report_file/report.txt")


def test_build_download_path_is_deterministic_and_sanitized(script_module, tmp_path: Path) -> None:
    url = "https://cdn.cse.lk/cmt/upload_report_file/431_1778641511402.03.2026.pdf"
    first = script_module._build_download_path(tmp_path, ticker="SAMP.N0000", url=url)
    second = script_module._build_download_path(tmp_path, ticker="SAMP.N0000", url=url)

    assert first == second
    assert first.parent == tmp_path
    assert first.name.startswith("cse_report_SAMP.N0000_431_1778641511402.03.2026_")
    assert first.suffix == ".pdf"


def test_main_downloads_and_ingests_cse_pdf_url(
    script_module,
    tmp_path: Path,
    patch_pypdf_reader,
    monkeypatch,
    capsys,
) -> None:
    download_dir = tmp_path / "downloads"
    store_path = tmp_path / "store" / "documents.jsonl"
    url = "https://cdn.cse.lk/cmt/upload_report_file/431_1778641511402.03.2026.pdf"
    expected_download_path = script_module._build_download_path(
        download_dir,
        ticker="SAMP.N0000",
        url=url,
    )
    patch_pypdf_reader(page_texts_by_name={expected_download_path.name: ["Interim statement text"]})

    def fake_download(download_url: str, destination: Path, *, timeout: float) -> None:
        assert download_url == url
        assert timeout == 20.0
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_simple_pdf(destination, "Interim statement text")

    monkeypatch.setattr(script_module, "_download_pdf", fake_download)

    exit_code = script_module.main(
        [
            "--url",
            url,
            "--ticker",
            "SAMP.N0000",
            "--company",
            "Sampath Bank PLC",
            "--title",
            "Sampath Bank PLC Interim Financial Statements 31 March 2026",
            "--announcement-type",
            "INTERIM_FINANCIAL_STATEMENTS",
            "--published-at",
            "2026-03-31T09:00:00Z",
            "--download-dir",
            str(download_dir),
            "--store",
            str(store_path),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "R10 CSE PDF URL Ingestion" in captured
    assert "ticker: SAMP.N0000" in captured
    assert "source_url: https://cdn.cse.lk/cmt/upload_report_file/431_1778641511402.03.2026.pdf" in captured
    assert "downloaded PDF path:" in captured
    assert "store path:" in captured

    documents = LocalDocumentStore(store_path).load_all()
    assert len(documents) == 1
    assert documents[0].title == "Sampath Bank PLC Interim Financial Statements 31 March 2026"
    assert documents[0].tickers_hint == ["SAMP.N0000"]
    assert documents[0].published_at == datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)
    assert documents[0].metadata["source"] == "CSE"
    assert documents[0].metadata["company"] == "Sampath Bank PLC"
    assert documents[0].metadata["announcement_type"] == "INTERIM_FINANCIAL_STATEMENTS"
    assert documents[0].metadata["source_url"] == url
    downloaded_pdfs = list(download_dir.glob("*.pdf"))
    assert len(downloaded_pdfs) == 1


def test_main_returns_failure_for_invalid_url(script_module, capsys) -> None:
    exit_code = script_module.main(
        [
            "--url",
            "https://example.com/report.pdf",
            "--ticker",
            "SAMP.N0000",
        ]
    )

    assert exit_code == 2
    assert "must point to cdn.cse.lk" in capsys.readouterr().out


def test_main_returns_failure_when_downloaded_file_is_not_pdf(
    script_module,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    download_dir = tmp_path / "downloads"
    store_path = tmp_path / "store" / "documents.jsonl"

    def fake_download(download_url: str, destination: Path, *, timeout: float) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("not a pdf", encoding="utf-8")

    monkeypatch.setattr(script_module, "_download_pdf", fake_download)

    exit_code = script_module.main(
        [
            "--url",
            "https://cdn.cse.lk/cmt/upload_report_file/report.pdf",
            "--ticker",
            "SAMP.N0000",
            "--download-dir",
            str(download_dir),
            "--store",
            str(store_path),
        ]
    )

    assert exit_code == 2
    assert "does not appear to be a valid PDF" in capsys.readouterr().out
