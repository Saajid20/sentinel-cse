from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.ingestion import (  # noqa: E402
    PdfFileDocumentSource,
    TextFileDocumentSource,
    ingest_documents,
)
from sentinel_research.agents.schemas import SourceType  # noqa: E402

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md"}
SUPPORTED_PDF_EXTENSION = ".pdf"
RESERVED_METADATA_KEYS = {
    "file_path",
    "file_name",
    "ingestion_source",
    "bootstrap_source",
    "ticker",
}


def _non_empty_value(name: str) -> Callable[[str], str]:
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _parse_source_type(value: str) -> SourceType:
    normalized = value.strip().upper()
    try:
        return SourceType(normalized)
    except ValueError as error:
        allowed = ", ".join(source_type.value for source_type in SourceType)
        raise argparse.ArgumentTypeError(
            f"Invalid source type {value!r}. Expected one of: {allowed}"
        ) from error


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO timestamp {value!r}. Expected ISO-8601 format."
        ) from error


def _parse_metadata_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--metadata must use key=value format")
    key, metadata_value = value.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("--metadata key must not be empty")
    if key in RESERVED_METADATA_KEYS:
        raise argparse.ArgumentTypeError(
            f"--metadata key {key!r} is reserved and cannot be overridden"
        )
    return key, metadata_value.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap one already-local source file into a Sentinel-CSE R10 "
            "LocalDocumentStore JSONL file."
        )
    )
    parser.add_argument(
        "--input-file",
        required=True,
        type=_non_empty_value("input_file"),
        help="Path to an existing local .txt, .md, or .pdf source file.",
    )
    parser.add_argument(
        "--output-store",
        required=True,
        type=_non_empty_value("output_store"),
        help="Path to the LocalDocumentStore JSONL file to write.",
    )
    parser.add_argument(
        "--source-type",
        required=True,
        type=_parse_source_type,
        help="Source type. Expected one of: CBSL, CSE_DISCLOSURE, NEWS, DAILY_FT, OTHER.",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        type=_non_empty_value("ticker"),
        help="Ticker hint to store with the source document.",
    )
    parser.add_argument(
        "--title",
        required=True,
        type=_non_empty_value("title"),
        help="Document title to store with the source document.",
    )
    parser.add_argument("--url", help="Optional original source URL.")
    parser.add_argument(
        "--published-at",
        type=_parse_iso_timestamp,
        help="Optional source published timestamp in ISO-8601 format.",
    )
    parser.add_argument(
        "--retrieved-at",
        type=_parse_iso_timestamp,
        help="Optional deterministic retrieval timestamp in ISO-8601 format.",
    )
    parser.add_argument(
        "--sector",
        action="append",
        default=[],
        help="Optional sector hint. May be passed multiple times.",
    )
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        type=_parse_metadata_pair,
        help="Optional metadata as key=value. May be passed multiple times.",
    )
    parser.add_argument(
        "--mode",
        choices=("append", "upsert"),
        default="upsert",
        help="Store write mode. Default: upsert.",
    )
    return parser


def _validate_input_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"input file does not exist: {path}")
    if path.is_dir():
        raise ValueError(f"input file is a directory: {path}")
    if not path.is_file():
        raise ValueError(f"input path is not a file: {path}")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_TEXT_EXTENSIONS and extension != SUPPORTED_PDF_EXTENSION:
        raise ValueError(
            "unsupported input file extension: "
            f"{path.suffix or path.name}; expected .txt, .md, or .pdf"
        )


def _build_now(args) -> Callable[[], datetime]:
    if args.retrieved_at is not None:
        return lambda: args.retrieved_at
    return lambda: datetime.now(timezone.utc)


def _build_metadata(args) -> dict[str, str]:
    metadata = {key: value for key, value in args.metadata}
    metadata["bootstrap_source"] = "local_file"
    metadata["ticker"] = args.ticker
    return metadata


def _build_source(args, input_file: Path):
    common_kwargs = {
        "source_type": args.source_type,
        "title": args.title,
        "url": args.url,
        "published_at": args.published_at,
        "tickers_hint": [args.ticker],
        "sectors_hint": args.sector,
        "metadata": _build_metadata(args),
        "now": _build_now(args),
    }
    if input_file.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return TextFileDocumentSource(input_file, **common_kwargs)
    return PdfFileDocumentSource(input_file, **common_kwargs)


def _print_success(
    *,
    input_file: Path,
    output_store: Path,
    source_type: SourceType,
    ticker: str,
    document_id: str,
    mode: str,
) -> None:
    print("R10 local document store bootstrap: PASS")
    print(f"input_file: {input_file}")
    print(f"output_store: {output_store}")
    print(f"source_type: {source_type.value}")
    print(f"ticker: {ticker}")
    print(f"document_id: {document_id}")
    print(f"mode: {mode}")


def _print_failure(input_file: str | None, reasons: list[str]) -> None:
    print("R10 local document store bootstrap: FAIL")
    print(f"input_file: {input_file or 'unavailable'}")
    print("reason:")
    for reason in reasons:
        print(f"* {reason}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    input_file = Path(args.input_file).expanduser()
    output_store = Path(args.output_store).expanduser()

    try:
        _validate_input_file(input_file)
        if output_store.exists() and output_store.is_dir():
            raise ValueError(f"output store is a directory: {output_store}")

        source = _build_source(args, input_file)
        store = LocalDocumentStore(output_store)
        result = ingest_documents(
            source,
            store,
            source_name="local_file_bootstrap",
            mode=args.mode,
        )
        if result.errors:
            raise ValueError("; ".join(result.errors))
        if result.stored_count != 1 or len(result.document_ids) != 1:
            raise ValueError(
                "expected exactly one SourceDocument to be stored; "
                f"stored_count={result.stored_count}"
            )

        _print_success(
            input_file=input_file,
            output_store=output_store,
            source_type=args.source_type,
            ticker=args.ticker,
            document_id=result.document_ids[0],
            mode=args.mode,
        )
        return 0
    except ValueError as error:
        _print_failure(args.input_file, [str(error)])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
