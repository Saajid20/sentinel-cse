from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    AggregatedMetricResult,
    MetricVerificationResult,
    ScorecardBuildResult,
)
from sentinel_research.agents.r11.extraction.statement_locator import (  # noqa: E402
    StatementPageMatch,
)
from sentinel_research.agents.r11.schemas import FinancialStatementType  # noqa: E402
from sentinel_research.agents.r11.validation import (  # noqa: E402
    ChecklistItemLevel,
    ChecklistResultStatus,
    PdfValidationChecklist,
    PdfValidationChecklistEvaluation,
    PdfValidationChecklistItem,
    PdfValidationChecklistResult,
    PdfValidationEvidence,
    evaluate_pdf_validation_checklist,
)


@dataclass(frozen=True)
class ExpectedPageCheck:
    page_number: int
    statement_type: FinancialStatementType


@dataclass(frozen=True)
class ValidationCliOptions:
    expected_pages: list[ExpectedPageCheck]
    min_verified_metrics: int | None = None
    min_aggregated_metrics: int | None = None
    expect_manual_review: bool | None = None
    require_scorecard: bool = False
    require_no_conflicts: bool = False


@dataclass(frozen=True)
class AnalysisValidationContext:
    analysis_path: Path
    payload: dict[str, object]
    statement_classifications: list[StatementPageMatch]
    verified_metric_results: list[MetricVerificationResult]
    aggregated_metric_results: list[AggregatedMetricResult]
    scorecard_build_result: ScorecardBuildResult | None


@dataclass(frozen=True)
class AnalysisValidationRunResult:
    context: AnalysisValidationContext
    evaluation: PdfValidationChecklistEvaluation


def _positive_int(name: str):
    def _parser(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from error
        if parsed < 0:
            raise argparse.ArgumentTypeError(f"{name} must be >= 0")
        return parsed

    return _parser


def _parse_bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("value must be true or false")


def _parse_expected_page_arg(value: str) -> ExpectedPageCheck:
    try:
        raw_page_number, raw_statement_type = value.split(":", maxsplit=1)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected page must be in PAGE:STATEMENT_TYPE format"
        ) from error

    raw_page_number = raw_page_number.strip()
    raw_statement_type = raw_statement_type.strip()
    if not raw_page_number:
        raise argparse.ArgumentTypeError("expected page number must not be empty")
    if not raw_statement_type:
        raise argparse.ArgumentTypeError("expected statement type must not be empty")

    try:
        page_number = int(raw_page_number)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected page number must be an integer") from error
    if page_number <= 0:
        raise argparse.ArgumentTypeError("expected page number must be positive")

    try:
        statement_type = FinancialStatementType(raw_statement_type.upper())
    except ValueError as error:
        valid_values = ", ".join(item.value for item in FinancialStatementType)
        raise argparse.ArgumentTypeError(
            f"expected statement type must be one of: {valid_values}"
        ) from error

    return ExpectedPageCheck(
        page_number=page_number,
        statement_type=statement_type,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually validate deterministic R11 analysis JSON against CLI checklist expectations."
    )
    parser.add_argument(
        "--analysis-json",
        required=True,
        help="Path to an existing deterministic R11 analysis JSON file.",
    )
    parser.add_argument(
        "--expect-page",
        action="append",
        default=[],
        type=_parse_expected_page_arg,
        help="Repeatable PAGE:STATEMENT_TYPE expectation, for example 5:INCOME_STATEMENT.",
    )
    parser.add_argument(
        "--min-verified-metrics",
        type=_positive_int("min-verified-metrics"),
        help="Minimum number of verified metric results required.",
    )
    parser.add_argument(
        "--min-aggregated-metrics",
        type=_positive_int("min-aggregated-metrics"),
        help="Minimum number of aggregated metric results required.",
    )
    parser.add_argument(
        "--expect-manual-review",
        type=_parse_bool_arg,
        help="Expected scorecard manual_review_required value: true or false.",
    )
    parser.add_argument(
        "--require-scorecard",
        action="store_true",
        help="Require scorecard_build_result.scorecard to be present.",
    )
    parser.add_argument(
        "--require-no-conflicts",
        action="store_true",
        help="Escalate to manual review if any aggregated metric conflicts are present.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output path for the validation result JSON.",
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


def _load_analysis_validation_context(path: Path) -> AnalysisValidationContext:
    payload = _load_analysis_payload(path)
    return AnalysisValidationContext(
        analysis_path=path,
        payload=payload,
        statement_classifications=_parse_statement_classifications(payload),
        verified_metric_results=_parse_verified_metric_results(payload),
        aggregated_metric_results=_parse_aggregated_metric_results(payload),
        scorecard_build_result=_parse_scorecard_build_result(payload),
    )


def _parse_statement_classifications(payload: dict[str, object]) -> list[StatementPageMatch]:
    raw_matches = payload.get("statement_classifications", [])
    if not isinstance(raw_matches, list):
        raise ValueError("statement_classifications must be a list")
    return [StatementPageMatch.model_validate(item) for item in raw_matches]


def _parse_verified_metric_results(payload: dict[str, object]) -> list[MetricVerificationResult]:
    raw_results = payload.get("verified_metric_results", [])
    if not isinstance(raw_results, list):
        raise ValueError("verified_metric_results must be a list")
    return [MetricVerificationResult.model_validate(item) for item in raw_results]


def _parse_aggregated_metric_results(payload: dict[str, object]) -> list[AggregatedMetricResult]:
    raw_results = payload.get("aggregated_metric_results", [])
    if not isinstance(raw_results, list):
        raise ValueError("aggregated_metric_results must be a list")
    return [AggregatedMetricResult.model_validate(item) for item in raw_results]


def _parse_scorecard_build_result(
    payload: dict[str, object],
) -> ScorecardBuildResult | None:
    raw_scorecard = payload.get("scorecard_build_result")
    if raw_scorecard is None:
        return None
    return ScorecardBuildResult.model_validate(raw_scorecard)


def _validation_options_from_args(args: argparse.Namespace) -> ValidationCliOptions:
    return ValidationCliOptions(
        expected_pages=list(args.expect_page),
        min_verified_metrics=args.min_verified_metrics,
        min_aggregated_metrics=args.min_aggregated_metrics,
        expect_manual_review=args.expect_manual_review,
        require_scorecard=bool(args.require_scorecard),
        require_no_conflicts=bool(args.require_no_conflicts),
    )


def parse_validation_cli_request(
    argv: list[str],
) -> tuple[Path, ValidationCliOptions]:
    args = _build_parser().parse_args(argv)
    return Path(args.analysis_json).expanduser(), _validation_options_from_args(args)


def _build_validation_checklist(
    options: ValidationCliOptions,
) -> PdfValidationChecklist:
    items: list[PdfValidationChecklistItem] = []

    for expectation in options.expected_pages:
        items.append(
            PdfValidationChecklistItem(
                item_id=f"expect_page_{expectation.page_number}_{expectation.statement_type.value}",
                title=f"Page {expectation.page_number} classified as {expectation.statement_type.value}",
                description="Statement classification must contain the requested page and statement type.",
                level=ChecklistItemLevel.REQUIRED,
                tags=["statement_classification", "page_expectation"],
            )
        )

    if options.min_verified_metrics is not None:
        items.append(
            PdfValidationChecklistItem(
                item_id="min_verified_metrics",
                title=f"Verified metric count >= {options.min_verified_metrics}",
                description="Verified metric result count must meet the manual validation threshold.",
                level=ChecklistItemLevel.REQUIRED,
                tags=["verified_metrics", "count_threshold"],
            )
        )

    if options.min_aggregated_metrics is not None:
        items.append(
            PdfValidationChecklistItem(
                item_id="min_aggregated_metrics",
                title=f"Aggregated metric count >= {options.min_aggregated_metrics}",
                description="Aggregated metric result count must meet the manual validation threshold.",
                level=ChecklistItemLevel.REQUIRED,
                tags=["aggregated_metrics", "count_threshold"],
            )
        )

    if options.expect_manual_review is not None:
        items.append(
            PdfValidationChecklistItem(
                item_id="expect_manual_review",
                title=f"Scorecard manual review expected == {options.expect_manual_review}",
                description="scorecard_build_result.scorecard.manual_review_required must match the CLI expectation.",
                level=ChecklistItemLevel.REQUIRED,
                tags=["scorecard", "manual_review_expectation"],
            )
        )

    if options.require_scorecard:
        items.append(
            PdfValidationChecklistItem(
                item_id="require_scorecard",
                title="Scorecard is present",
                description="scorecard_build_result and scorecard_build_result.scorecard must exist.",
                level=ChecklistItemLevel.REQUIRED,
                tags=["scorecard", "presence"],
            )
        )

    if options.require_no_conflicts:
        items.append(
            PdfValidationChecklistItem(
                item_id="require_no_conflicts",
                title="No aggregated metric conflicts",
                description="Aggregated metric conflicts should escalate to manual review.",
                level=ChecklistItemLevel.ADVISORY,
                tags=["aggregated_metrics", "conflict_review"],
            )
        )

    if not items:
        raise ValueError("At least one validation expectation must be provided")

    return PdfValidationChecklist(
        checklist_id="r11_analysis_json_manual_validation",
        title="R11 Analysis JSON Manual Validation",
        items=items,
    )


def _build_validation_results(
    context: AnalysisValidationContext,
    options: ValidationCliOptions,
) -> list[PdfValidationChecklistResult]:
    results: list[PdfValidationChecklistResult] = []

    for expectation in options.expected_pages:
        results.append(_evaluate_expected_page(context, expectation))

    if options.min_verified_metrics is not None:
        results.append(
            _evaluate_min_count(
                item_id="min_verified_metrics",
                actual_count=len(context.verified_metric_results),
                expected_minimum=options.min_verified_metrics,
                count_label="verified_metric_results",
            )
        )

    if options.min_aggregated_metrics is not None:
        results.append(
            _evaluate_min_count(
                item_id="min_aggregated_metrics",
                actual_count=len(context.aggregated_metric_results),
                expected_minimum=options.min_aggregated_metrics,
                count_label="aggregated_metric_results",
            )
        )

    if options.expect_manual_review is not None:
        results.append(
            _evaluate_expect_manual_review(
                context,
                expected_manual_review=options.expect_manual_review,
            )
        )

    if options.require_scorecard:
        results.append(_evaluate_require_scorecard(context))

    if options.require_no_conflicts:
        results.append(_evaluate_require_no_conflicts(context))

    return results


def _evaluate_expected_page(
    context: AnalysisValidationContext,
    expectation: ExpectedPageCheck,
) -> PdfValidationChecklistResult:
    for match in context.statement_classifications:
        if (
            match.page_number == expectation.page_number
            and match.statement_type is expectation.statement_type
        ):
            return PdfValidationChecklistResult(
                item_id=f"expect_page_{expectation.page_number}_{expectation.statement_type.value}",
                status=ChecklistResultStatus.PASS,
                notes=(
                    f"Found {expectation.statement_type.value} on page "
                    f"{expectation.page_number}."
                ),
                evidence=[
                    PdfValidationEvidence(
                        page_number=match.page_number,
                        table_id=match.table_id,
                        locator_text=", ".join(match.matched_markers)
                        if match.matched_markers
                        else expectation.statement_type.value,
                        note=match.notes,
                    )
                ],
            )

    return PdfValidationChecklistResult(
        item_id=f"expect_page_{expectation.page_number}_{expectation.statement_type.value}",
        status=ChecklistResultStatus.FAIL,
        notes=(
            f"Missing {expectation.statement_type.value} classification on page "
            f"{expectation.page_number}."
        ),
        evidence=[
            PdfValidationEvidence(
                page_number=expectation.page_number,
                locator_text=expectation.statement_type.value,
                note="Expected statement classification was not present in analysis JSON.",
            )
        ],
    )


def _evaluate_min_count(
    *,
    item_id: str,
    actual_count: int,
    expected_minimum: int,
    count_label: str,
) -> PdfValidationChecklistResult:
    status = (
        ChecklistResultStatus.PASS
        if actual_count >= expected_minimum
        else ChecklistResultStatus.FAIL
    )
    comparator = ">=" if status is ChecklistResultStatus.PASS else "<"
    return PdfValidationChecklistResult(
        item_id=item_id,
        status=status,
        notes=(
            f"{count_label} count {actual_count} {comparator} "
            f"required minimum {expected_minimum}."
        ),
    )


def _evaluate_expect_manual_review(
    context: AnalysisValidationContext,
    *,
    expected_manual_review: bool,
) -> PdfValidationChecklistResult:
    if context.scorecard_build_result is None:
        return PdfValidationChecklistResult(
            item_id="expect_manual_review",
            status=ChecklistResultStatus.FAIL,
            notes="scorecard_build_result is missing; manual review expectation could not be checked.",
        )

    actual_manual_review = context.scorecard_build_result.scorecard.manual_review_required
    status = (
        ChecklistResultStatus.PASS
        if actual_manual_review is expected_manual_review
        else ChecklistResultStatus.FAIL
    )
    return PdfValidationChecklistResult(
        item_id="expect_manual_review",
        status=status,
        notes=(
            f"scorecard.manual_review_required={actual_manual_review}; "
            f"expected {expected_manual_review}."
        ),
    )


def _evaluate_require_scorecard(
    context: AnalysisValidationContext,
) -> PdfValidationChecklistResult:
    if context.scorecard_build_result is None:
        return PdfValidationChecklistResult(
            item_id="require_scorecard",
            status=ChecklistResultStatus.FAIL,
            notes="scorecard_build_result is missing.",
        )

    return PdfValidationChecklistResult(
        item_id="require_scorecard",
        status=ChecklistResultStatus.PASS,
        notes="scorecard_build_result.scorecard is present.",
    )


def _evaluate_require_no_conflicts(
    context: AnalysisValidationContext,
) -> PdfValidationChecklistResult:
    conflicting_metrics = [
        item.metric_name for item in context.aggregated_metric_results if item.conflict
    ]
    if not conflicting_metrics:
        return PdfValidationChecklistResult(
            item_id="require_no_conflicts",
            status=ChecklistResultStatus.PASS,
            notes="No aggregated metric conflicts were present.",
        )

    return PdfValidationChecklistResult(
        item_id="require_no_conflicts",
        status=ChecklistResultStatus.MANUAL_REVIEW,
        notes=(
            "Aggregated metric conflicts require manual review: "
            + ", ".join(conflicting_metrics)
            + "."
        ),
    )


def run_validation_checklist(
    context: AnalysisValidationContext,
    options: ValidationCliOptions,
) -> PdfValidationChecklistEvaluation:
    checklist = _build_validation_checklist(options)
    results = _build_validation_results(context, options)
    return evaluate_pdf_validation_checklist(checklist, results)


def validate_analysis_json_path(
    analysis_path: Path,
    options: ValidationCliOptions,
) -> AnalysisValidationRunResult:
    context = _load_analysis_validation_context(analysis_path)
    evaluation = run_validation_checklist(context, options)
    return AnalysisValidationRunResult(
        context=context,
        evaluation=evaluation,
    )


def _validation_output_payload(
    context: AnalysisValidationContext,
    evaluation: PdfValidationChecklistEvaluation,
) -> dict[str, object]:
    payload = evaluation.model_dump(mode="json")
    payload["analysis_json"] = str(context.analysis_path.resolve())
    return payload


def _write_validation_output_json(
    output_path: Path,
    context: AnalysisValidationContext,
    evaluation: PdfValidationChecklistEvaluation,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_validation_output_payload(context, evaluation), indent=2),
        encoding="utf-8",
        newline="\n",
    )


def _print_compact_validation_output(
    context: AnalysisValidationContext,
    evaluation: PdfValidationChecklistEvaluation,
) -> None:
    print("R11 Analysis JSON Validation")
    print(f"analysis_json: {context.analysis_path.resolve()}")
    print(f"overall result: {evaluation.overall_status.value}")
    print(f"passed count: {evaluation.passed_items}")
    print(f"failed count: {evaluation.failed_items}")
    print(f"manual review count: {evaluation.manual_review_items}")
    for item in evaluation.evaluations:
        notes = item.notes or ""
        print(f"{item.item_id}: {item.status.value} {notes}".rstrip())


def _exit_code_from_evaluation(
    evaluation: PdfValidationChecklistEvaluation,
) -> int:
    if evaluation.overall_status.value == "PASS":
        return 0
    if evaluation.overall_status.value == "MANUAL_REVIEW":
        return 1
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        run_result = validate_analysis_json_path(
            Path(args.analysis_json).expanduser(),
            _validation_options_from_args(args),
        )

        _print_compact_validation_output(
            run_result.context,
            run_result.evaluation,
        )

        if args.output_json:
            _write_validation_output_json(
                Path(args.output_json).expanduser(),
                run_result.context,
                run_result.evaluation,
            )

        return _exit_code_from_evaluation(run_result.evaluation)
    except (ValueError, ValidationError) as error:
        print(f"R11 analysis JSON validation failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 analysis JSON validation failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
