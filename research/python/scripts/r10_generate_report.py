from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import ContextAgent, DeepSeekProvider, R10AnalysisError  # noqa: E402
from sentinel_research.agents.analysis import RetrievedContextAnalyzer  # noqa: E402
from sentinel_research.agents.documents import LocalDocumentStore  # noqa: E402
from sentinel_research.agents.reports import (  # noqa: E402
    LocalReportStore,
    R10AnalysisReport,
    ReportType,
    build_report_id,
)
from sentinel_research.agents.retrieval import DocumentQuery  # noqa: E402
from sentinel_research.agents.schemas import SourceType  # noqa: E402

DEFAULT_REPORTS_DIR = PYTHON_ROOT / ".r10_runtime" / "reports"


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _parse_iso_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO timestamp {value!r}. Expected ISO-8601 format."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated-at must be timezone-aware")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a manual offline R10 analysis report from an existing LocalDocumentStore."
    )
    parser.add_argument(
        "--store",
        required=True,
        help="Path to an existing LocalDocumentStore JSONL file.",
    )
    parser.add_argument(
        "--report-type",
        required=True,
        choices=[report_type.value for report_type in ReportType],
        help="Offline report type to generate.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Retrieval keyword. May be passed multiple times.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Ticker filter. May be passed multiple times.",
    )
    parser.add_argument(
        "--sector",
        action="append",
        default=[],
        help="Sector filter. May be passed multiple times.",
    )
    parser.add_argument(
        "--source-type",
        action="append",
        default=[],
        choices=[source_type.value for source_type in SourceType],
        help="Source type filter. May be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum documents to analyze. Default: 3.",
    )
    parser.add_argument(
        "--scope-key",
        type=_non_empty_value("scope_key"),
        help="Optional scope value used in the report_id.",
    )
    parser.add_argument(
        "--notes",
        help="Optional report notes.",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory where offline report JSON files are written.",
    )
    parser.add_argument(
        "--generated-at",
        type=_parse_iso_timestamp,
        help="Optional ISO-8601 timestamp for deterministic report generation.",
    )
    return parser


def _build_query(args: argparse.Namespace) -> DocumentQuery:
    return DocumentQuery(
        keywords=args.query,
        tickers=args.ticker,
        sectors=args.sector,
        source_types=args.source_type,
        limit=args.limit,
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("R10 report generation requires DEEPSEEK_API_KEY to be set in the environment.")
        return 1

    try:
        store_path = Path(args.store).expanduser()
        if not store_path.exists() or not store_path.is_file():
            raise ValueError(f"LocalDocumentStore path does not exist: {store_path}")

        report_type = ReportType(args.report_type)
        generated_at = args.generated_at or datetime.now(UTC)

        store = LocalDocumentStore(store_path)
        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        analyzer = RetrievedContextAnalyzer(store, agent)

        query = _build_query(args)
        analysis = analyzer.analyze(query)

        report = R10AnalysisReport(
            report_id=build_report_id(report_type, generated_at, args.scope_key),
            report_type=report_type,
            generated_at=generated_at,
            query=query.model_dump(mode="json"),
            analysis=analysis,
            source_document_ids=[],
            notes=args.notes,
        )

        report_store = LocalReportStore(Path(args.reports_dir).expanduser())
        report_path = report_store.save(report)

        print("R10 Offline Report Generated")
        print(f"report path: {report_path}")
        print(f"report_id: {report.report_id}")
        print(f"report_type: {report.report_type.value}")
        print(f"analysis_scope: {report.analysis.analysis_scope.value}")
        print(f"ticker: {report.analysis.ticker}")
        print(f"sector: {report.analysis.sector}")
        print(f"macro_risk_level: {report.analysis.macro_risk_level.value}")
        print(f"sentiment: {report.analysis.sentiment.value}")
        print(f"signal_policy: {report.analysis.signal_policy.value}")
        print(f"manual_review_required: {report.analysis.manual_review_required}")
        print(f"source count: {len(report.analysis.sources)}")
        return 0
    except (ValueError, R10AnalysisError) as error:
        print(f"R10 report generation failed: {error}")
        return 2
    except Exception as error:
        print(f"R10 report generation failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
