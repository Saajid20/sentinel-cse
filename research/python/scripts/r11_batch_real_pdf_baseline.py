from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from scripts import r10_fetch_cse_pdf_url as fetch_script  # noqa: E402
from scripts import r10_lookup_cse_financial_reports as lookup_script  # noqa: E402
from scripts import r11_inspect_pypdf_baseline as inspect_script  # noqa: E402
from scripts.r11_validate_manifest import (  # noqa: E402
    build_manifest_report_payload,
    run_manifest_case,
)
from sentinel_research.agents.ingestion import (  # noqa: E402
    CseApiClient,
    CseApiError,
    CseFinancialReport,
)
from sentinel_research.agents.r11.validation import (  # noqa: E402
    ExpectedStatementPage,
    R11ValidationCase,
    R11ValidationManifest,
    save_validation_manifest,
)

DEFAULT_R10_PDF_DIR = fetch_script.DEFAULT_DOWNLOAD_DIR
DEFAULT_R11_ANALYSIS_DIR = PYTHON_ROOT / ".r11_runtime" / "analysis"
DEFAULT_R11_VALIDATION_DIR = PYTHON_ROOT / ".r11_runtime" / "validation"
DEFAULT_REPORT_PATH = DEFAULT_R11_VALIDATION_DIR / "r11_batch_real_pdf_baseline_report.json"
DEFAULT_MANIFEST_PATH = DEFAULT_R11_VALIDATION_DIR / "r11_batch_real_pdf_baseline_manifest.json"
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _normalize_required_str(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _sanitize_name(value: str) -> str:
    sanitized = _SAFE_NAME_PATTERN.sub("_", value.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("._")
    return sanitized or "case"


def _safe_case_id(ticker: str) -> str:
    return _sanitize_name(ticker).lower().replace(".", "_") + "_real_pdf_baseline"


def _analysis_file_name_for_report(report: CseFinancialReport, *, ticker: str) -> str:
    pdf_path = resolve_pdf_path_for_report(report, ticker=ticker)
    return f"{pdf_path.stem}_analysis.json"


def resolve_pdf_path_for_report(report: CseFinancialReport, *, ticker: str) -> Path:
    return fetch_script._build_download_path(
        DEFAULT_R10_PDF_DIR,
        ticker=ticker,
        url=report.full_url,
    )


def resolve_analysis_path_for_report(report: CseFinancialReport, *, ticker: str) -> Path:
    return DEFAULT_R11_ANALYSIS_DIR / _analysis_file_name_for_report(report, ticker=ticker)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class BatchCandidateCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    report_text_filter: str | None = None
    preferred_report_type: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    expected_pages: list[ExpectedStatementPage] = Field(default_factory=list)
    min_verified_metrics: int | None = None
    min_aggregated_metrics: int | None = None
    expect_manual_review: bool | None = None
    selected_report_id: int | None = None
    notes: str | None = None

    @field_validator(
        "ticker",
        "company_name",
        "report_text_filter",
        "preferred_report_type",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_text(cls, value: str | None, info):
        if info.field_name == "ticker":
            if value is None:
                raise ValueError("ticker must not be empty")
            return _normalize_required_str(value, "ticker")
        return _normalize_optional_str(value)

    @field_validator("min_verified_metrics", "min_aggregated_metrics")
    @classmethod
    def _validate_non_negative_int(cls, value: int | None, info):
        if value is not None and value < 0:
            raise ValueError(f"{info.field_name} must be >= 0")
        return value


class BatchCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "r11_batch_real_pdf_baseline_config_v1"
    cases: list[BatchCandidateCase]
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "r11_batch_real_pdf_baseline_config_v1":
            raise ValueError(
                'schema_version must be "r11_batch_real_pdf_baseline_config_v1"'
            )
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: str | None) -> str | None:
        return _normalize_optional_str(value)

    @field_validator("cases")
    @classmethod
    def _validate_cases(cls, value: list[BatchCandidateCase]) -> list[BatchCandidateCase]:
        if not value:
            raise ValueError("cases must not be empty")
        return value


@dataclass(frozen=True)
class ReportSelection:
    status: str
    selected_report: CseFinancialReport | None
    matching_reports: list[CseFinancialReport]
    reason: str


@dataclass
class BatchCaseResult:
    ticker: str
    company_name: str | None
    lookup_status: str
    selection_reason: str | None = None
    selected_report_id: int | None = None
    selected_report_title: str | None = None
    pdf_url: str | None = None
    local_pdf_path: str | None = None
    analysis_json_path: str | None = None
    classified_pages: list[str] = field(default_factory=list)
    validation_status: str | None = None
    manual_review_needed: bool | None = None
    expectation_needed: bool = False
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "lookup_status": self.lookup_status,
            "selection_reason": self.selection_reason,
            "selected_report_id": self.selected_report_id,
            "selected_report_title": self.selected_report_title,
            "pdf_url": self.pdf_url,
            "local_pdf_path": self.local_pdf_path,
            "analysis_json_path": self.analysis_json_path,
            "classified_pages": self.classified_pages,
            "validation_status": self.validation_status,
            "manual_review_needed": self.manual_review_needed,
            "expectation_needed": self.expectation_needed,
            "notes": list(self.notes),
            "error": self.error,
        }


def load_batch_candidate_config(path: str | Path) -> BatchCandidateConfig:
    config_path = Path(path).expanduser()
    if not config_path.exists() or not config_path.is_file():
        raise ValueError(f"Batch config path does not exist: {config_path}")

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Batch config JSON is invalid: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError("Batch config payload must be an object")

    try:
        return BatchCandidateConfig.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"Batch config is invalid: {error}") from error


def load_financial_reports(*, base_url: str, timeout: float) -> list[CseFinancialReport]:
    client = CseApiClient(base_url=base_url, timeout=timeout)
    return client.get_financial_reports()


def _report_matches_preferred_type(
    report: CseFinancialReport,
    preferred_report_type: str | None,
) -> bool:
    if preferred_report_type is None:
        return True
    normalized = preferred_report_type.strip().lower()
    haystack = " ".join(
        value
        for value in (report.file_text, report.name, report.path)
        if value
    ).lower()
    return normalized in haystack


def lookup_matching_reports(
    case: BatchCandidateCase,
    reports: list[CseFinancialReport],
) -> list[CseFinancialReport]:
    filtered = lookup_script.filter_financial_reports(
        reports,
        ticker=case.ticker,
        from_date=case.from_date,
        to_date=case.to_date,
        text_filter=case.report_text_filter,
    )
    filtered = [
        report
        for report in filtered
        if _report_matches_preferred_type(report, case.preferred_report_type)
    ]
    return sorted(
        filtered,
        key=lambda report: (
            lookup_script._report_effective_date(report) or date.min,
            report.id or -1,
        ),
        reverse=True,
    )


def select_report_for_case(
    case: BatchCandidateCase,
    matching_reports: list[CseFinancialReport],
) -> ReportSelection:
    if not matching_reports:
        return ReportSelection(
            status="NOT_FOUND",
            selected_report=None,
            matching_reports=[],
            reason="No matching financial reports were found.",
        )

    if case.selected_report_id is not None:
        for report in matching_reports:
            if report.id == case.selected_report_id:
                return ReportSelection(
                    status="SELECTED",
                    selected_report=report,
                    matching_reports=matching_reports,
                    reason=f"Selected explicitly by report id {case.selected_report_id}.",
                )
        return ReportSelection(
            status="AMBIGUOUS",
            selected_report=None,
            matching_reports=matching_reports,
            reason=(
                f"selected_report_id={case.selected_report_id} did not match any "
                "candidate report."
            ),
        )

    if len(matching_reports) == 1:
        return ReportSelection(
            status="SELECTED",
            selected_report=matching_reports[0],
            matching_reports=matching_reports,
            reason="Single matching financial report.",
        )

    newest = matching_reports[0]
    newest_date = lookup_script._report_effective_date(newest)
    if newest_date is None:
        return ReportSelection(
            status="AMBIGUOUS",
            selected_report=None,
            matching_reports=matching_reports,
            reason=(
                "Multiple matching reports were found and the newest candidate "
                "could not be determined unambiguously."
            ),
        )

    top_date_matches = [
        report
        for report in matching_reports
        if lookup_script._report_effective_date(report) == newest_date
    ]
    if len(top_date_matches) == 1:
        return ReportSelection(
            status="SELECTED",
            selected_report=newest,
            matching_reports=matching_reports,
            reason=f"Selected newest unambiguous report dated {newest_date.isoformat()}.",
        )

    return ReportSelection(
        status="AMBIGUOUS",
        selected_report=None,
        matching_reports=matching_reports,
        reason=(
            f"Multiple matching reports share the newest date {newest_date.isoformat()}; "
            "manual selection is required."
        ),
    )


def fetch_selected_report_pdf(
    report: CseFinancialReport,
    *,
    ticker: str,
    timeout: float,
) -> Path:
    resolved_url = fetch_script._validate_cse_pdf_url(report.full_url)
    destination = resolve_pdf_path_for_report(report, ticker=ticker)
    fetch_script._download_pdf(resolved_url, destination, timeout=timeout)
    return destination


def inspect_local_pdf(
    *,
    pdf_path: Path,
    analysis_path: Path,
    metric_entity: str,
) -> dict[str, object]:
    stdout_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer):
        exit_code = inspect_script.main(
            [
                "--pdf",
                str(pdf_path),
                "--metric-entity",
                metric_entity,
                "--show-scorecard",
                "--output-analysis-json",
                str(analysis_path),
            ]
        )
    captured_output = stdout_buffer.getvalue()
    if captured_output:
        print(captured_output, end="")
    if exit_code != 0:
        error_message = _extract_inspection_error_message(captured_output)
        raise ValueError(error_message)
    return _load_json(analysis_path)


def _extract_inspection_error_message(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        prefix = "R11 pypdf baseline inspection failed:"
        if line.startswith(prefix):
            remainder = line[len(prefix) :].strip()
            return remainder or line
    return "R11 inspection failed unexpectedly."


def _inspect_failure_note(error_message: str) -> str | None:
    normalized = error_message.strip().lower()
    if "no extractable baseline table/text pages found" in normalized:
        return "OCR_NEEDED"
    if "invalid financial value" in normalized:
        return "PARSE_ERROR"
    return None


def _statement_pages_from_analysis_payload(payload: dict[str, object]) -> list[str]:
    matches = payload.get("statement_classifications", [])
    if not isinstance(matches, list):
        return []

    pages: list[str] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        page_number = item.get("page_number")
        statement_type = item.get("statement_type")
        if page_number is None or statement_type is None:
            continue
        pages.append(f"{page_number}:{statement_type}")
    return pages


def _manual_review_from_analysis_payload(payload: dict[str, object]) -> bool | None:
    scorecard = payload.get("scorecard_build_result")
    if not isinstance(scorecard, dict):
        return None
    nested_scorecard = scorecard.get("scorecard")
    if not isinstance(nested_scorecard, dict):
        return None
    manual_review = nested_scorecard.get("manual_review_required")
    return manual_review if isinstance(manual_review, bool) else None


def _build_manifest_case(
    case: BatchCandidateCase,
    *,
    analysis_path: Path,
) -> R11ValidationCase:
    return R11ValidationCase(
        case_id=_safe_case_id(case.ticker),
        ticker=case.ticker,
        company_name=case.company_name,
        description="Controlled real-PDF baseline case.",
        analysis_json_path=str(analysis_path.resolve()),
        expected_pages=case.expected_pages,
        min_verified_metrics=case.min_verified_metrics,
        min_aggregated_metrics=case.min_aggregated_metrics,
        expect_manual_review=case.expect_manual_review,
        require_scorecard=True,
        require_no_conflicts=True,
        notes=case.notes,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled helper for local real-PDF R11 baseline lookup, fetch, "
            "inspection, and validation. Unknown cases are never auto-approved."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the batch candidate JSON config file.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--lookup-only",
        action="store_true",
        help="Lookup candidate reports and print matches without downloading PDFs.",
    )
    mode_group.add_argument(
        "--fetch",
        action="store_true",
        help="Download selected PDFs into .r10_runtime only.",
    )
    mode_group.add_argument(
        "--inspect",
        action="store_true",
        help="Run deterministic R11 inspection against existing local PDFs.",
    )
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate only cases with expected_pages using existing analysis JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without downloading or writing runtime outputs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing local PDFs or analysis JSONs.",
    )
    parser.add_argument(
        "--metric-entity",
        choices=("group", "bank"),
        default="group",
        help="Entity prefix to use for R11 inspection.",
    )
    parser.add_argument(
        "--report-json",
        help=(
            "Optional output path for the local batch report JSON. Defaults to "
            ".r11_runtime/validation/r11_batch_real_pdf_baseline_report.json "
            "for fetch/inspect/validate modes."
        ),
    )
    parser.add_argument(
        "--manifest-json",
        help=(
            "Optional manifest path for validate mode. Defaults to "
            ".r11_runtime/validation/r11_batch_real_pdf_baseline_manifest.json."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="https://www.cse.lk/api",
        type=lookup_script._non_empty_value("base_url"),
        help="CSE API base URL.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    return parser


def _print_lookup_candidates(case: BatchCandidateCase, reports: list[CseFinancialReport]) -> None:
    print()
    print(f"lookup candidates for {case.ticker}: count={len(reports)}")
    for index, report in enumerate(reports, start=1):
        lookup_script._print_report(report, index=index)


def _apply_selection_to_result(
    result: BatchCaseResult,
    selection: ReportSelection,
    *,
    ticker: str,
) -> CseFinancialReport | None:
    result.lookup_status = selection.status
    result.selection_reason = selection.reason
    if selection.selected_report is None:
        if selection.reason:
            result.notes.append(selection.reason)
        return None

    report = selection.selected_report
    result.selected_report_id = report.id
    result.selected_report_title = report.file_text or report.name or report.path
    result.pdf_url = report.full_url
    result.local_pdf_path = str(resolve_pdf_path_for_report(report, ticker=ticker))
    return report


def _result_for_case(case: BatchCandidateCase) -> BatchCaseResult:
    return BatchCaseResult(
        ticker=case.ticker,
        company_name=case.company_name,
        lookup_status="PENDING",
    )


def run_lookup_only_mode(
    config: BatchCandidateConfig,
    *,
    reports: list[CseFinancialReport],
) -> list[BatchCaseResult]:
    results: list[BatchCaseResult] = []
    for case in config.cases:
        result = _result_for_case(case)
        matching_reports = lookup_matching_reports(case, reports)
        if matching_reports:
            result.lookup_status = "MATCHED"
            result.notes.append(f"Found {len(matching_reports)} matching report(s).")
        else:
            result.lookup_status = "NOT_FOUND"
            result.notes.append("No matching reports found.")
        results.append(result)
        _print_lookup_candidates(case, matching_reports)
    return results


def run_fetch_mode(
    config: BatchCandidateConfig,
    *,
    reports: list[CseFinancialReport],
    timeout: float,
    dry_run: bool,
    force: bool,
) -> list[BatchCaseResult]:
    results: list[BatchCaseResult] = []
    for case in config.cases:
        result = _result_for_case(case)
        matching_reports = lookup_matching_reports(case, reports)
        selection = select_report_for_case(case, matching_reports)
        report = _apply_selection_to_result(result, selection, ticker=case.ticker)
        results.append(result)
        if report is None:
            continue

        pdf_path = resolve_pdf_path_for_report(report, ticker=case.ticker)
        if dry_run:
            result.notes.append(f"Dry run: would download PDF to {pdf_path}.")
            continue

        if pdf_path.exists() and not force:
            result.notes.append(f"Using existing local PDF: {pdf_path}")
            continue

        fetch_selected_report_pdf(report, ticker=case.ticker, timeout=timeout)
        result.notes.append(f"Downloaded PDF to {pdf_path}")
    return results


def run_inspect_mode(
    config: BatchCandidateConfig,
    *,
    reports: list[CseFinancialReport],
    metric_entity: str,
    dry_run: bool,
    force: bool,
) -> list[BatchCaseResult]:
    results: list[BatchCaseResult] = []
    for case in config.cases:
        result = _result_for_case(case)
        matching_reports = lookup_matching_reports(case, reports)
        selection = select_report_for_case(case, matching_reports)
        report = _apply_selection_to_result(result, selection, ticker=case.ticker)
        results.append(result)
        if report is None:
            continue

        pdf_path = resolve_pdf_path_for_report(report, ticker=case.ticker)
        analysis_path = resolve_analysis_path_for_report(report, ticker=case.ticker)
        if not pdf_path.exists():
            result.validation_status = "INSPECT_FAILED"
            result.expectation_needed = True
            result.error = f"Local PDF does not exist: {pdf_path}"
            result.notes.append("Run --fetch first or place the PDF in .r10_runtime.")
            continue

        if dry_run:
            result.validation_status = "INSPECT_PENDING"
            result.notes.append(
                f"Dry run: would inspect {pdf_path} and write {analysis_path}."
            )
            continue

        if analysis_path.exists() and not force:
            payload = _load_json(analysis_path)
            result.analysis_json_path = str(analysis_path)
            result.validation_status = "INSPECTED"
            result.notes.append(f"Using existing analysis JSON: {analysis_path}")
        else:
            try:
                payload = inspect_local_pdf(
                    pdf_path=pdf_path,
                    analysis_path=analysis_path,
                    metric_entity=metric_entity,
                )
            except ValueError as error:
                result.validation_status = "INSPECT_FAILED"
                result.expectation_needed = True
                result.error = str(error)
                failure_note = _inspect_failure_note(result.error)
                if failure_note is not None:
                    result.notes.append(failure_note)
                result.notes.append("Inspection failed; manual follow-up is required.")
                continue
            result.analysis_json_path = str(analysis_path)
            result.validation_status = "INSPECTED"
            result.notes.append(f"Saved analysis JSON: {analysis_path}")

        result.classified_pages = _statement_pages_from_analysis_payload(payload)
        result.manual_review_needed = _manual_review_from_analysis_payload(payload)
    return results


def run_validate_mode(
    config: BatchCandidateConfig,
    *,
    reports: list[CseFinancialReport],
    dry_run: bool,
    manifest_path: Path,
) -> tuple[list[BatchCaseResult], dict[str, object] | None]:
    results: list[BatchCaseResult] = []
    manifest_cases: list[R11ValidationCase] = []

    for case in config.cases:
        result = _result_for_case(case)
        matching_reports = lookup_matching_reports(case, reports)
        selection = select_report_for_case(case, matching_reports)
        report = _apply_selection_to_result(result, selection, ticker=case.ticker)
        results.append(result)
        if report is None:
            continue

        analysis_path = resolve_analysis_path_for_report(report, ticker=case.ticker)
        if not case.expected_pages:
            result.validation_status = "EXPECTATION_NEEDED"
            result.expectation_needed = True
            result.notes.append(
                "Validation skipped because expected_pages were not supplied."
            )
            continue

        if not analysis_path.exists():
            result.validation_status = "ANALYSIS_MISSING"
            result.notes.append(
                "Validation skipped because the local analysis JSON does not exist."
            )
            continue

        manifest_case = _build_manifest_case(case, analysis_path=analysis_path)
        manifest_cases.append(manifest_case)
        result.validation_status = "QUEUED"

    if dry_run:
        for result in results:
            if result.validation_status == "QUEUED":
                result.notes.append("Dry run: would include case in validation manifest.")
        return results, None

    if not manifest_cases:
        return results, None

    manifest = R11ValidationManifest(cases=manifest_cases, notes=config.notes)
    save_validation_manifest(manifest, manifest_path)
    case_results = [run_manifest_case(manifest_path, case) for case in manifest.cases]
    manifest_report_payload = build_manifest_report_payload(manifest_path, case_results)

    results_by_case_id = {
        _safe_case_id(result.ticker): result
        for result in results
        if result.lookup_status == "SELECTED"
    }
    for case_result in case_results:
        result = results_by_case_id.get(case_result.case_id)
        if result is None:
            continue
        result.validation_status = case_result.overall_result
        result.manual_review_needed = case_result.manual_review_count > 0
        if case_result.error:
            result.error = case_result.error

    return results, manifest_report_payload


def _print_summary_table(results: list[BatchCaseResult]) -> None:
    print()
    print("R11 Batch Real PDF Baseline Summary")
    print(
        "ticker | lookup_status | selected_report | local_pdf_path | "
        "analysis_json_path | classified_pages | validation_status | expectation_needed"
    )
    for result in results:
        print(
            " | ".join(
                [
                    result.ticker,
                    result.lookup_status,
                    result.selected_report_title or "-",
                    result.local_pdf_path or "-",
                    result.analysis_json_path or "-",
                    ",".join(result.classified_pages) or "-",
                    result.validation_status or "-",
                    "true" if result.expectation_needed else "false",
                ]
            )
        )
        for note in result.notes:
            print(f"  note: {note}")
        if result.error:
            print(f"  error: {result.error}")


def _report_payload(
    *,
    mode: str,
    config_path: Path,
    results: list[BatchCaseResult],
    manifest_path: Path | None = None,
    manifest_report_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "r11_batch_real_pdf_baseline_report_v1",
        "mode": mode,
        "config_path": str(config_path.resolve()),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "manifest_path": None if manifest_path is None else str(manifest_path.resolve()),
        "manifest_report": manifest_report_payload,
        "case_results": [result.to_payload() for result in results],
    }


def _write_report_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def _default_report_path_for_args(args: argparse.Namespace) -> Path | None:
    if args.lookup_only or args.dry_run:
        return None
    return DEFAULT_REPORT_PATH


def _exit_code_from_results(
    *,
    mode: str,
    results: list[BatchCaseResult],
    manifest_report_payload: dict[str, object] | None,
) -> int:
    if mode == "inspect":
        return 0
    if any(result.error is not None for result in results):
        return 1
    if any(result.lookup_status in {"NOT_FOUND", "AMBIGUOUS"} for result in results):
        return 1
    if mode == "validate":
        if any(result.expectation_needed for result in results):
            return 1
        if manifest_report_payload is None:
            return 1
        manifest_case_results = manifest_report_payload.get("case_results", [])
        if not isinstance(manifest_case_results, list):
            return 1
        statuses = [
            item.get("overall_result")
            for item in manifest_case_results
            if isinstance(item, dict)
        ]
        if any(status == "FAIL" for status in statuses):
            return 2
        if any(status == "MANUAL_REVIEW" for status in statuses):
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        config_path = Path(args.config).expanduser()
        config = load_batch_candidate_config(config_path)
        reports = load_financial_reports(base_url=args.base_url, timeout=args.timeout)
        manifest_report_payload = None
        manifest_path = Path(args.manifest_json).expanduser() if args.manifest_json else DEFAULT_MANIFEST_PATH

        if args.lookup_only:
            mode = "lookup_only"
            results = run_lookup_only_mode(config, reports=reports)
        elif args.fetch:
            mode = "fetch"
            results = run_fetch_mode(
                config,
                reports=reports,
                timeout=args.timeout,
                dry_run=bool(args.dry_run),
                force=bool(args.force),
            )
        elif args.inspect:
            mode = "inspect"
            results = run_inspect_mode(
                config,
                reports=reports,
                metric_entity=args.metric_entity,
                dry_run=bool(args.dry_run),
                force=bool(args.force),
            )
        else:
            mode = "validate"
            results, manifest_report_payload = run_validate_mode(
                config,
                reports=reports,
                dry_run=bool(args.dry_run),
                manifest_path=manifest_path,
            )

        _print_summary_table(results)

        report_path = (
            Path(args.report_json).expanduser()
            if args.report_json
            else _default_report_path_for_args(args)
        )
        if report_path is not None and not args.dry_run:
            _write_report_json(
                report_path,
                _report_payload(
                    mode=mode,
                    config_path=config_path,
                    results=results,
                    manifest_path=(manifest_path if mode == "validate" else None),
                    manifest_report_payload=manifest_report_payload,
                ),
            )
            print()
            print(f"saved batch report json: {report_path.resolve()}")

        return _exit_code_from_results(
            mode=mode,
            results=results,
            manifest_report_payload=manifest_report_payload,
        )
    except (CseApiError, ValueError) as error:
        print(f"R11 batch real PDF baseline failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 batch real PDF baseline failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
