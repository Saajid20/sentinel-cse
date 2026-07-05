from __future__ import annotations

import io
import re
import sys
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PYTHON_ROOT / "scripts"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import bootstrap_r10_local_document_store as script_module  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import pdf_source as pdf_source_module  # noqa: E402
from sentinel_research.agents.schemas import SourceType  # noqa: E402


@pytest.fixture
def tmp_path() -> Path:
    base = PYTHON_ROOT / ".pytest_tmp"
    base.mkdir(exist_ok=True)
    path = base / f"r10-local-store-bootstrap-{uuid4().hex}"
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


def run_cli(args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = script_module.main(args)
    return exit_code, buffer.getvalue()


def base_args(input_file: Path, output_store: Path) -> list[str]:
    return [
        "--input-file",
        str(input_file),
        "--output-store",
        str(output_store),
        "--source-type",
        "CSE_DISCLOSURE",
        "--ticker",
        "PKME.N0000",
        "--title",
        "PKME local source document",
    ]


def assert_no_action_language(text: str) -> None:
    assert re.search(r"\b(?:BUY|SELL|HOLD|ENTRY|EXIT|TRADE)\b", text) is None


def test_cli_parses_required_args() -> None:
    parser = script_module.build_parser()

    args = parser.parse_args(
        [
            "--input-file",
            "source.txt",
            "--output-store",
            "documents.jsonl",
            "--source-type",
            "CBSL",
            "--ticker",
            "PKME.N0000",
            "--title",
            "Local source",
        ]
    )

    assert args.input_file == "source.txt"
    assert args.output_store == "documents.jsonl"
    assert args.source_type == SourceType.CBSL
    assert args.ticker == "PKME.N0000"
    assert args.title == "Local source"
    assert args.mode == "upsert"


def test_cli_parses_optional_args() -> None:
    parser = script_module.build_parser()

    args = parser.parse_args(
        [
            "--input-file",
            "source.pdf",
            "--output-store",
            "documents.jsonl",
            "--source-type",
            "NEWS",
            "--ticker",
            "PKME.N0000",
            "--title",
            "Local source",
            "--url",
            "https://example.com/source.pdf",
            "--published-at",
            "2026-06-02T09:00:00Z",
            "--retrieved-at",
            "2026-06-02T10:00:00Z",
            "--sector",
            "TECHNOLOGY",
            "--sector",
            "TRANSPORT",
            "--metadata",
            "company=Digital Mobility Solutions Lanka PLC",
            "--mode",
            "append",
        ]
    )

    assert args.source_type == SourceType.NEWS
    assert args.url == "https://example.com/source.pdf"
    assert args.published_at == datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc)
    assert args.retrieved_at == datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    assert args.sector == ["TECHNOLOGY", "TRANSPORT"]
    assert args.metadata == [("company", "Digital Mobility Solutions Lanka PLC")]
    assert args.mode == "append"


def test_missing_input_file_fails_cleanly(tmp_path: Path) -> None:
    exit_code, output = run_cli(base_args(tmp_path / "missing.txt", tmp_path / "documents.jsonl"))

    assert exit_code == 2
    assert "R10 local document store bootstrap: FAIL" in output
    assert "input file does not exist" in output
    assert "Traceback" not in output


def test_directory_input_fails_cleanly(tmp_path: Path) -> None:
    exit_code, output = run_cli(base_args(tmp_path, tmp_path / "documents.jsonl"))

    assert exit_code == 2
    assert "input file is a directory" in output
    assert "Traceback" not in output


def test_unsupported_extension_fails_cleanly(tmp_path: Path) -> None:
    input_file = tmp_path / "source.csv"
    input_file.write_text("PKME.N0000 local source text", encoding="utf-8")

    exit_code, output = run_cli(base_args(input_file, tmp_path / "documents.jsonl"))

    assert exit_code == 2
    assert "unsupported input file extension" in output
    assert not (tmp_path / "documents.jsonl").exists()
    assert "Traceback" not in output


def test_txt_creates_one_valid_source_document_in_requested_store(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "store" / "documents.jsonl"
    input_file.write_text("PKME.N0000 local disclosure text", encoding="utf-8")

    exit_code, output = run_cli(
        base_args(input_file, store_path)
        + ["--retrieved-at", "2026-06-02T10:00:00Z"]
    )
    documents = LocalDocumentStore(store_path).load_all()

    assert exit_code == 0
    assert "R10 local document store bootstrap: PASS" in output
    assert len(documents) == 1
    assert documents[0].source_type == SourceType.CSE_DISCLOSURE
    assert documents[0].title == "PKME local source document"
    assert documents[0].raw_text == "PKME.N0000 local disclosure text"
    assert documents[0].normalized_text == "PKME.N0000 local disclosure text"
    assert documents[0].tickers_hint == ["PKME.N0000"]
    assert documents[0].retrieved_at == datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    assert documents[0].metadata["file_path"] == str(input_file.resolve())
    assert documents[0].metadata["file_name"] == "source.txt"
    assert documents[0].metadata["bootstrap_source"] == "local_file"
    assert documents[0].metadata["ticker"] == "PKME.N0000"
    assert_no_action_language(output)
    assert_no_action_language(store_path.read_text(encoding="utf-8"))


def test_md_creates_one_valid_source_document_in_requested_store(tmp_path: Path) -> None:
    input_file = tmp_path / "source.md"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("# PKME\n\nLocal source note.", encoding="utf-8")

    exit_code, _ = run_cli(base_args(input_file, store_path))
    documents = LocalDocumentStore(store_path).load_all()

    assert exit_code == 0
    assert len(documents) == 1
    assert documents[0].raw_text == "# PKME\n\nLocal source note."
    assert documents[0].metadata["file_name"] == "source.md"


def test_pdf_uses_existing_pdf_file_document_source(
    tmp_path: Path,
    patch_pypdf_reader,
) -> None:
    input_file = tmp_path / "source.pdf"
    store_path = tmp_path / "documents.jsonl"
    write_simple_pdf(input_file, "PDF local source")
    patch_pypdf_reader(page_texts_by_name={"source.pdf": ["PDF local source"]})

    exit_code, output = run_cli(base_args(input_file, store_path))
    documents = LocalDocumentStore(store_path).load_all()

    assert exit_code == 0
    assert "source_type: CSE_DISCLOSURE" in output
    assert len(documents) == 1
    assert documents[0].raw_text == "PDF local source"
    assert documents[0].metadata["ingestion_source"] == "pdf_file"
    assert documents[0].metadata["page_count"] == 1


def test_retrieved_at_makes_output_deterministic(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 deterministic source", encoding="utf-8")
    args = base_args(input_file, store_path) + ["--retrieved-at", "2026-06-02T10:00:00Z"]

    first_exit, first_output = run_cli(args)
    first_store_text = store_path.read_text(encoding="utf-8")
    second_exit, second_output = run_cli(args)
    second_store_text = store_path.read_text(encoding="utf-8")

    assert first_exit == 0
    assert second_exit == 0
    assert first_output == second_output
    assert first_store_text == second_store_text


def test_default_mode_is_upsert(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 upsert source", encoding="utf-8")

    exit_code, output = run_cli(base_args(input_file, store_path))

    assert exit_code == 0
    assert "mode: upsert" in output


def test_append_mode_appends(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 append source", encoding="utf-8")
    args = base_args(input_file, store_path) + [
        "--retrieved-at",
        "2026-06-02T10:00:00Z",
        "--mode",
        "append",
    ]

    first_exit, _ = run_cli(args)
    second_exit, _ = run_cli(args)
    documents = LocalDocumentStore(store_path).load_all()

    assert first_exit == 0
    assert second_exit == 0
    assert len(documents) == 2
    assert documents[0].document_id == documents[1].document_id


def test_upsert_mode_avoids_duplicate_rows_for_repeatable_runs(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 upsert repeatable source", encoding="utf-8")
    args = base_args(input_file, store_path) + [
        "--retrieved-at",
        "2026-06-02T10:00:00Z",
        "--mode",
        "upsert",
    ]

    first_exit, _ = run_cli(args)
    second_exit, _ = run_cli(args)
    documents = LocalDocumentStore(store_path).load_all()

    assert first_exit == 0
    assert second_exit == 0
    assert len(documents) == 1


def test_metadata_key_value_is_included(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 metadata source", encoding="utf-8")

    exit_code, _ = run_cli(
        base_args(input_file, store_path)
        + [
            "--metadata",
            "company=Digital Mobility Solutions Lanka PLC",
            "--metadata",
            "source_family=CSE",
        ]
    )
    document = LocalDocumentStore(store_path).load_all()[0]

    assert exit_code == 0
    assert document.metadata["company"] == "Digital Mobility Solutions Lanka PLC"
    assert document.metadata["source_family"] == "CSE"


def test_parent_output_directory_is_created_automatically(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "nested" / "store" / "documents.jsonl"
    input_file.write_text("PKME.N0000 nested store source", encoding="utf-8")

    exit_code, _ = run_cli(base_args(input_file, store_path))

    assert exit_code == 0
    assert store_path.exists()


def test_no_network_analyzer_or_provider_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 local-only source", encoding="utf-8")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network call should not happen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    exit_code, output = run_cli(base_args(input_file, store_path))

    assert exit_code == 0
    assert "PASS" in output
    assert not hasattr(script_module, "ContextAgent")
    assert not hasattr(script_module, "RetrievedContextAnalyzer")
    assert not hasattr(script_module, "DeepSeekProvider")


def test_no_files_written_except_requested_output_store(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 single output source", encoding="utf-8")
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    exit_code, _ = run_cli(base_args(input_file, store_path))
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert exit_code == 0
    assert before == [Path("source.txt")]
    assert after == [Path("documents.jsonl"), Path("source.txt")]


def test_normal_failures_do_not_print_traceback_text(tmp_path: Path) -> None:
    input_file = tmp_path / "source.html"
    input_file.write_text("<p>unsupported</p>", encoding="utf-8")

    exit_code, output = run_cli(base_args(input_file, tmp_path / "documents.jsonl"))

    assert exit_code == 2
    assert "Traceback" not in output


def test_output_contains_no_action_language_tokens(tmp_path: Path) -> None:
    input_file = tmp_path / "source.txt"
    store_path = tmp_path / "documents.jsonl"
    input_file.write_text("PKME.N0000 local source text", encoding="utf-8")

    exit_code, output = run_cli(base_args(input_file, store_path))

    assert exit_code == 0
    assert_no_action_language(output)
    assert_no_action_language(store_path.read_text(encoding="utf-8"))
