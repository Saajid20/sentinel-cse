from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.validation.gold_label import (  # noqa: E402
    GoldLabelValidationResult,
    GoldLabelValidationStatus,
    validate_gold_label_paths,
    write_gold_label_validation_result_json,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an R11 gold-label expected-output JSON file against an R11 analysis JSON file."
    )
    parser.add_argument(
        "--gold-label",
        required=True,
        help="Path to the R11 gold-label expected-output JSON file.",
    )
    parser.add_argument(
        "--analysis-json",
        required=True,
        help="Path to the deterministic R11 analysis JSON file.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output path for the structured validation result JSON.",
    )
    return parser


def _print_validation_result(
    *,
    gold_label_path: Path,
    analysis_json_path: Path,
    result: GoldLabelValidationResult,
) -> None:
    print("R11 Gold-Label Validation")
    print(f"gold_label: {gold_label_path.resolve()}")
    print(f"analysis_json: {analysis_json_path.resolve()}")
    print(f"overall result: {result.overall_result.value}")
    print(f"passed count: {result.passed_count}")
    print(f"failed count: {result.failed_count}")
    print(f"manual review count: {result.manual_review_count}")
    for check in result.checks:
        print(f"{check.check_id}: {check.status.value} {check.message}")


def _exit_code_from_result(result: GoldLabelValidationResult) -> int:
    if result.overall_result is GoldLabelValidationStatus.PASS:
        return 0
    if result.overall_result is GoldLabelValidationStatus.MANUAL_REVIEW:
        return 1
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        gold_label_path = Path(args.gold_label).expanduser()
        analysis_json_path = Path(args.analysis_json).expanduser()
        result = validate_gold_label_paths(
            gold_label_path=gold_label_path,
            analysis_json_path=analysis_json_path,
        )
        _print_validation_result(
            gold_label_path=gold_label_path,
            analysis_json_path=analysis_json_path,
            result=result,
        )
        if args.output_json:
            write_gold_label_validation_result_json(
                result=result,
                output_path=Path(args.output_json).expanduser(),
                gold_label_path=gold_label_path,
                analysis_json_path=analysis_json_path,
            )
        return _exit_code_from_result(result)
    except ValueError as error:
        print(f"R11 gold-label validation failed: {error}")
        return 2
    except Exception as error:
        print(f"R11 gold-label validation failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
