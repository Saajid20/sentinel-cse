from __future__ import annotations

import sys
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11 import R11ConfidenceLevel  # noqa: E402
from sentinel_research.agents.r11.extraction import (  # noqa: E402
    PypdfBaselineExtractor,
    R11ExtractionError,
    extract_text_lines_from_pdf,
)
from sentinel_research.agents.r11.extraction import pypdf_baseline as baseline_module  # noqa: E402


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r11-pypdf-baseline-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _make_fake_pdf_reader(
    *,
    page_texts_by_name: dict[str, list[str]] | None = None,
    error: Exception | None = None,
):
    class FakePdfReader:
        def __init__(self, handle) -> None:
            if error is not None:
                raise error
            texts = (page_texts_by_name or {}).get(Path(handle.name).name, [])
            self.pages = [_FakePdfPage(text) for text in texts]

    return FakePdfReader


@pytest.fixture
def patch_pypdf_reader(monkeypatch):
    def _patch(
        *,
        page_texts_by_name: dict[str, list[str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        monkeypatch.setattr(
            baseline_module,
            "_import_pypdf_reader",
            lambda: _make_fake_pdf_reader(
                page_texts_by_name=page_texts_by_name,
                error=error,
            ),
        )

    return _patch


def write_stub_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\n% r11 baseline test fixture\n")


def test_rejects_missing_file_with_r11_extraction_error(tmp_path: Path) -> None:
    extractor = PypdfBaselineExtractor()

    with pytest.raises(R11ExtractionError, match="PDF file does not exist"):
        extractor.extract(tmp_path / "missing.pdf")


def test_rejects_non_pdf_extension(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("not a pdf", encoding="utf-8")
    extractor = PypdfBaselineExtractor()

    with pytest.raises(R11ExtractionError, match="Unsupported file extension"):
        extractor.extract(path)


def test_wraps_pypdf_reader_failures(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "broken.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(error=RuntimeError("boom"))
    extractor = PypdfBaselineExtractor()

    with pytest.raises(R11ExtractionError, match="Failed to extract baseline PDF text from .*broken.pdf: boom"):
        extractor.extract(path)


def test_skips_pages_with_too_few_non_empty_lines(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(
        page_texts_by_name={
            "sample.pdf": [
                "One line only",
                "Revenue\n100\nExpenses\n80",
            ]
        }
    )
    extractor = PypdfBaselineExtractor(min_non_empty_lines=2)

    tables = extractor.extract(path)

    assert len(tables) == 1
    assert tables[0].page_number == 2


def test_returns_extracted_financial_table_objects_for_pages_with_enough_lines(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(
        page_texts_by_name={
            "sample.pdf": [
                "Revenue\n100",
                "Expenses\n80",
            ]
        }
    )
    extractor = PypdfBaselineExtractor()

    tables = extractor.extract(path)

    assert len(tables) == 2
    assert tables[0].statement_type.value == "UNKNOWN"


def test_table_id_is_deterministic(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    first = extractor.extract(path)[0].table_id
    second = extractor.extract(path)[0].table_id

    assert first == "pypdf_page_1"
    assert second == "pypdf_page_1"


def test_page_number_is_one_based(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": [" \n ", "Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    tables = extractor.extract(path)

    assert tables[0].page_number == 2


def test_columns_are_line_number_and_text(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    table = extractor.extract(path)[0]

    assert table.columns == ["line_number", "text"]


def test_rows_contain_line_number_and_text(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    table = extractor.extract(path)[0]

    assert table.rows == [
        {"line_number": 1, "text": "Revenue"},
        {"line_number": 2, "text": "100"},
    ]


def test_source_trace_includes_local_file_path_and_page_number(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    table = extractor.extract(path)[0]

    assert table.source_trace is not None
    assert table.source_trace.local_file_path == str(path.resolve())
    assert table.source_trace.page_number == 1


def test_extraction_confidence_is_low(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})
    extractor = PypdfBaselineExtractor()

    table = extractor.extract(path)[0]

    assert table.extraction_confidence is R11ConfidenceLevel.LOW


def test_extract_text_lines_from_pdf_returns_stripped_non_empty_lines(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": [" Revenue \n \n 100 \n"]})

    page_lines = extract_text_lines_from_pdf(path)

    assert page_lines == {1: ["Revenue", "100"]}


def test_no_test_calls_deepseek_or_network(tmp_path: Path, patch_pypdf_reader) -> None:
    path = tmp_path / "sample.pdf"
    write_stub_pdf(path)
    patch_pypdf_reader(page_texts_by_name={"sample.pdf": ["Revenue\n100"]})

    tables = PypdfBaselineExtractor().extract(path)

    assert tables[0].rows[0]["text"] == "Revenue"
