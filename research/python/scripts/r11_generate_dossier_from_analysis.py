from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    AggregatedMetricResult,
    DeterministicDossierBuildInput,
    ScorecardBuildResult,
    build_deterministic_r11_dossier,
)
from sentinel_research.agents.r11.extraction.statement_locator import (  # noqa: E402
    StatementPageMatch,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialMetric,
    R11AnalystDossier,
    SourceTrace,
    ToolAuditEntry,
)


def _non_empty_value(name: str):
    def _parser(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise argparse.ArgumentTypeError(f"{name} must not be empty")
        return normalized

    return _parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an R11AnalystDossier JSON file from saved deterministic R11 analysis JSON."
    )
    parser.add_argument(
        "--analysis-json",
        required=True,
        help="Path to an existing deterministic R11 analysis JSON file.",
    )
    parser.add_argument(
        "--ticker",
        required=True,
        type=_non_empty_value("ticker"),
        help="Ticker symbol, for example COMB.N0000.",
    )
    parser.add_argument(
        "--company",
        type=_non_empty_value("company"),
        help="Optional company name override.",
    )
    parser.add_argument(
        "--title",
        type=_non_empty_value("title"),
        help="Optional analysis title.",
    )
    parser.add_argument(
        "--source-title",
        type=_non_empty_value("source-title"),
        help="Optional source document title.",
    )
    parser.add_argument(
        "--source-url",
        type=_non_empty_value("source-url"),
        help="Optional source document URL.",
    )
    parser.add_argument(
        "--output",
        help="Optional output path for the generated R11AnalystDossier JSON.",
    )
    return parser


def _load_analysis_payload(path: Path) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        raise ValueError(f"Deterministic analysis JSON path does not exist: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Deterministic analysis JSON is invalid: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError("Deterministic analysis JSON payload must be an object")

    schema_version = payload.get("schema_version")
    if schema_version != "r11_deterministic_analysis_v1":
        raise ValueError(
            "Deterministic analysis JSON schema_version must be "
            '"r11_deterministic_analysis_v1"'
        )

    return payload


def _extract_dossier_components(
    payload: dict[str, object],
) -> tuple[
    ScorecardBuildResult,
    list[AggregatedMetricResult],
    list[FinancialMetric],
    list[ToolAuditEntry],
    list[SourceTrace],
]:
    raw_scorecard = payload.get("scorecard_build_result")
    if raw_scorecard is None:
        raise ValueError("Deterministic analysis JSON is missing scorecard_build_result")

    scorecard_result = ScorecardBuildResult.model_validate(raw_scorecard)

    raw_aggregated = payload.get("aggregated_metric_results", [])
    if not isinstance(raw_aggregated, list):
        raise ValueError("aggregated_metric_results must be a list")
    aggregated_metrics = [
        AggregatedMetricResult.model_validate(item) for item in raw_aggregated
    ]
    if not aggregated_metrics:
        raise ValueError("Deterministic analysis JSON must contain aggregated_metric_results")

    financial_metrics = [
        item.selected_metric.model_copy(deep=True) for item in aggregated_metrics
    ]
    tool_audit_entries = [
        item.selected_audit_entry.model_copy(deep=True) for item in aggregated_metrics
    ]

    source_traces = _statement_classifications_to_source_traces(payload)
    return (
        scorecard_result,
        aggregated_metrics,
        financial_metrics,
        tool_audit_entries,
        source_traces,
    )


def _statement_classifications_to_source_traces(
    payload: dict[str, object],
) -> list[SourceTrace]:
    raw_pdf_path = payload.get("pdf_path")
    pdf_path = str(raw_pdf_path).strip() if raw_pdf_path is not None else None
    raw_matches = payload.get("statement_classifications", [])
    if not isinstance(raw_matches, list):
        raise ValueError("statement_classifications must be a list")

    source_traces: list[SourceTrace] = []
    for raw_match in raw_matches:
        match = StatementPageMatch.model_validate(raw_match)
        source_traces.append(
            SourceTrace(
                local_file_path=pdf_path,
                page_number=match.page_number,
                table_id=match.table_id,
                row_label=match.statement_type.value,
                extracted_value=", ".join(match.matched_markers) if match.matched_markers else None,
                notes=_statement_match_note(match),
            )
        )
    return source_traces


def _statement_match_note(match: StatementPageMatch) -> str:
    markers = ", ".join(match.matched_markers) if match.matched_markers else "none"
    note = (
        f"statement_type={match.statement_type.value}; "
        f"confidence={match.confidence.value}; "
        f"matched_markers={markers}"
    )
    if match.notes:
        return f"{note}; notes={match.notes}"
    return note


def _default_output_path(dossier: R11AnalystDossier) -> Path:
    return PYTHON_ROOT / ".r11_runtime" / "dossiers" / f"{dossier.dossier_id}.json"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        analysis_path = Path(args.analysis_json).expanduser()
        payload = _load_analysis_payload(analysis_path)
        (
            scorecard_result,
            aggregated_metrics,
            financial_metrics,
            tool_audit_entries,
            source_traces,
        ) = _extract_dossier_components(payload)

        build_input = DeterministicDossierBuildInput(
            ticker=args.ticker,
            company_name=args.company,
            analysis_title=args.title,
            source_document_title=args.source_title,
            source_document_url=args.source_url,
            scorecard_result=scorecard_result,
            aggregated_metrics=aggregated_metrics,
            financial_metrics=financial_metrics,
            tool_audit_entries=tool_audit_entries,
            source_traces=source_traces,
            notes=f"analysis_json={analysis_path.resolve()}",
        )
        dossier = build_deterministic_r11_dossier(
            build_input,
            generated_at=datetime.now(UTC),
        )

        output_path = (
            Path(args.output).expanduser()
            if args.output
            else _default_output_path(dossier)
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            dossier.model_dump_json(indent=2),
            encoding="utf-8",
            newline="\n",
        )

        print("R11 Deterministic Dossier Generation")
        print(f"dossier path: {output_path.resolve()}")
        print(f"dossier_id: {dossier.dossier_id}")
        print(f"ticker: {dossier.ticker}")
        print(f"company_name: {dossier.company}")
        print(f"financial metric count: {len(dossier.financial_metrics)}")
        print(f"audit entry count: {len(dossier.tool_audit)}")
        print(f"red flag count: {len(dossier.accounting_red_flags)}")
        print(f"manual_review_required: {dossier.manual_review_required}")
        print(f"scorecard summary: {dossier.fundamental_scorecard.summary}")

        return 0
    except (ValueError, ValidationError) as error:
        print(f"R11 deterministic dossier generation failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 deterministic dossier generation failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
