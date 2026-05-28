from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from scripts.r11_validate_analysis_json import (  # noqa: E402
    AnalysisValidationRunResult,
    parse_validation_cli_request,
    validate_analysis_json_path,
)
from sentinel_research.agents.r11.validation import (  # noqa: E402
    R11ValidationCase,
    R11ValidationManifestError,
    load_validation_manifest,
    validation_case_to_cli_args,
)


@dataclass(frozen=True)
class ManifestCaseRunResult:
    case_id: str
    ticker: str | None
    analysis_json: str
    overall_result: str
    passed_count: int
    failed_count: int
    manual_review_count: int
    evaluation_payload: dict[str, object] | None = None
    error: str | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate all cases in an R11 validation manifest. Relative "
            "analysis_json_path values resolve against the manifest parent "
            "directory unless --base-dir is provided."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to an R11 validation manifest JSON file.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output path for the manifest validation report JSON.",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop after the first FAIL case. MANUAL_REVIEW does not stop execution.",
    )
    parser.add_argument(
        "--base-dir",
        help="Optional base directory for resolving relative analysis_json_path values.",
    )
    return parser


def resolve_case_analysis_json_path(
    manifest_path: Path,
    case: R11ValidationCase,
    base_dir: Path | None = None,
) -> Path:
    candidate = Path(case.analysis_json_path).expanduser()
    if candidate.is_absolute():
        return candidate

    resolution_root = base_dir.expanduser() if base_dir is not None else manifest_path.parent
    return (resolution_root / candidate).resolve()


def run_manifest_case(
    manifest_path: Path,
    case: R11ValidationCase,
    *,
    base_dir: Path | None = None,
) -> ManifestCaseRunResult:
    analysis_arg_path, options = parse_validation_cli_request(
        validation_case_to_cli_args(case)
    )
    resolved_analysis_path = resolve_case_analysis_json_path(
        manifest_path,
        case,
        base_dir=base_dir,
    )

    try:
        run_result = validate_analysis_json_path(resolved_analysis_path, options)
        return manifest_case_result_from_validation_run(
            case,
            run_result,
        )
    except (ValueError, ValidationError) as error:
        return ManifestCaseRunResult(
            case_id=case.case_id,
            ticker=case.ticker,
            analysis_json=str(resolved_analysis_path),
            overall_result="FAIL",
            passed_count=0,
            failed_count=1,
            manual_review_count=0,
            evaluation_payload=None,
            error=(
                f"analysis_json={analysis_arg_path} resolved_to={resolved_analysis_path}; "
                f"{error}"
            ),
        )


def manifest_case_result_from_validation_run(
    case: R11ValidationCase,
    run_result: AnalysisValidationRunResult,
) -> ManifestCaseRunResult:
    evaluation = run_result.evaluation
    evaluation_payload = evaluation.model_dump(mode="json")
    evaluation_payload["analysis_json"] = str(run_result.context.analysis_path.resolve())

    return ManifestCaseRunResult(
        case_id=case.case_id,
        ticker=case.ticker,
        analysis_json=str(run_result.context.analysis_path.resolve()),
        overall_result=evaluation.overall_status.value,
        passed_count=evaluation.passed_items,
        failed_count=evaluation.failed_items,
        manual_review_count=evaluation.manual_review_items,
        evaluation_payload=evaluation_payload,
        error=None,
    )


def build_manifest_report_payload(
    manifest_path: Path,
    case_results: list[ManifestCaseRunResult],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    generated_timestamp = generated_at or datetime.now(UTC)
    if generated_timestamp.tzinfo is None or generated_timestamp.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")

    cases_passed = sum(1 for item in case_results if item.overall_result == "PASS")
    cases_failed = sum(1 for item in case_results if item.overall_result == "FAIL")
    cases_manual_review = sum(
        1 for item in case_results if item.overall_result == "MANUAL_REVIEW"
    )

    return {
        "schema_version": "r11_validation_manifest_report_v1",
        "manifest_path": str(manifest_path.resolve()),
        "generated_at": generated_timestamp.isoformat().replace("+00:00", "Z"),
        "cases_total": len(case_results),
        "cases_passed": cases_passed,
        "cases_failed": cases_failed,
        "cases_manual_review": cases_manual_review,
        "case_results": [
            {
                "case_id": item.case_id,
                "ticker": item.ticker,
                "analysis_json": item.analysis_json,
                "overall_result": item.overall_result,
                "passed_count": item.passed_count,
                "failed_count": item.failed_count,
                "manual_review_count": item.manual_review_count,
                "evaluation": item.evaluation_payload,
                "error": item.error,
            }
            for item in case_results
        ],
    }


def write_manifest_report_json(
    output_path: Path,
    report_payload: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report_payload, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def print_manifest_summary(
    manifest_path: Path,
    case_results: list[ManifestCaseRunResult],
) -> None:
    cases_passed = sum(1 for item in case_results if item.overall_result == "PASS")
    cases_failed = sum(1 for item in case_results if item.overall_result == "FAIL")
    cases_manual_review = sum(
        1 for item in case_results if item.overall_result == "MANUAL_REVIEW"
    )

    print("R11 Validation Manifest")
    print(f"manifest path: {manifest_path.resolve()}")
    print(f"cases_total: {len(case_results)}")
    print(f"cases_passed: {cases_passed}")
    print(f"cases_failed: {cases_failed}")
    print(f"cases_manual_review: {cases_manual_review}")

    for item in case_results:
        ticker = item.ticker or "-"
        print(
            f"{item.case_id} ticker={ticker} overall_result={item.overall_result} "
            f"passed_count={item.passed_count} failed_count={item.failed_count} "
            f"manual_review_count={item.manual_review_count}"
        )


def exit_code_from_manifest_results(case_results: list[ManifestCaseRunResult]) -> int:
    if any(item.overall_result == "FAIL" for item in case_results):
        return 2
    if any(item.overall_result == "MANUAL_REVIEW" for item in case_results):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        manifest_path = Path(args.manifest).expanduser()
        manifest = load_validation_manifest(manifest_path)
        base_dir = Path(args.base_dir).expanduser() if args.base_dir else None

        case_results: list[ManifestCaseRunResult] = []
        for case in manifest.cases:
            result = run_manifest_case(
                manifest_path,
                case,
                base_dir=base_dir,
            )
            case_results.append(result)
            if args.stop_on_fail and result.overall_result == "FAIL":
                break

        print_manifest_summary(manifest_path, case_results)

        report_payload = build_manifest_report_payload(
            manifest_path,
            case_results,
        )
        if args.output_json:
            write_manifest_report_json(
                Path(args.output_json).expanduser(),
                report_payload,
            )

        return exit_code_from_manifest_results(case_results)
    except (R11ValidationManifestError, ValueError, ValidationError) as error:
        print(f"R11 validation manifest failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 validation manifest failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
