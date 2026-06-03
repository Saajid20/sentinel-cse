from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class GoldLabelValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class GoldLabelValidationCheck:
    check_id: str
    status: GoldLabelValidationStatus
    message: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class GoldLabelValidationResult:
    overall_result: GoldLabelValidationStatus
    passed_count: int
    failed_count: int
    manual_review_count: int
    checks: list[GoldLabelValidationCheck]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "overall_result": self.overall_result.value,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "manual_review_count": self.manual_review_count,
            "checks": [check.to_json_dict() for check in self.checks],
        }


def load_gold_label_case(path: Path) -> dict[str, object]:
    return _load_json_object(path, "gold-label JSON")


def load_analysis_json(path: Path) -> dict[str, object]:
    return _load_json_object(path, "R11 analysis JSON")


def validate_gold_label_paths(
    *,
    gold_label_path: Path,
    analysis_json_path: Path,
) -> GoldLabelValidationResult:
    return validate_gold_label_case(
        gold_label=load_gold_label_case(gold_label_path),
        analysis_json=load_analysis_json(analysis_json_path),
    )


def validate_gold_label_case(
    *,
    gold_label: dict[str, object],
    analysis_json: dict[str, object],
) -> GoldLabelValidationResult:
    checks: list[GoldLabelValidationCheck] = []
    checks.extend(_validate_expected_statement_pages(gold_label, analysis_json))
    checks.extend(_validate_expected_metrics(gold_label, analysis_json))
    checks.extend(_validate_expected_scorecard(gold_label, analysis_json))

    passed_count = sum(1 for check in checks if check.status is GoldLabelValidationStatus.PASS)
    failed_count = sum(1 for check in checks if check.status is GoldLabelValidationStatus.FAIL)
    manual_review_count = sum(
        1 for check in checks if check.status is GoldLabelValidationStatus.MANUAL_REVIEW
    )

    if failed_count:
        overall_result = GoldLabelValidationStatus.FAIL
    elif manual_review_count:
        overall_result = GoldLabelValidationStatus.MANUAL_REVIEW
    else:
        overall_result = GoldLabelValidationStatus.PASS

    return GoldLabelValidationResult(
        overall_result=overall_result,
        passed_count=passed_count,
        failed_count=failed_count,
        manual_review_count=manual_review_count,
        checks=checks,
    )


def write_gold_label_validation_result_json(
    *,
    result: GoldLabelValidationResult,
    output_path: Path,
    gold_label_path: Path | None = None,
    analysis_json_path: Path | None = None,
) -> None:
    payload = result.to_json_dict()
    if gold_label_path is not None:
        payload["gold_label"] = str(gold_label_path.resolve())
    if analysis_json_path is not None:
        payload["analysis_json"] = str(analysis_json_path.resolve())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        raise ValueError(f"{label} path does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} payload must be a JSON object")
    return payload


def _validate_expected_statement_pages(
    gold_label: dict[str, object],
    analysis_json: dict[str, object],
) -> list[GoldLabelValidationCheck]:
    checks: list[GoldLabelValidationCheck] = []
    statement_matches = _as_list(analysis_json.get("statement_classifications"))
    matches_by_page = {
        _optional_int(match.get("page_number")): match
        for match in statement_matches
        if isinstance(match, dict) and _optional_int(match.get("page_number")) is not None
    }

    for expected in _as_list(gold_label.get("expected_statement_pages")):
        if not isinstance(expected, dict):
            checks.append(
                GoldLabelValidationCheck(
                    check_id="statement_page_invalid",
                    status=GoldLabelValidationStatus.FAIL,
                    message="Expected statement page entry must be an object.",
                )
            )
            continue

        page_number = _optional_int(expected.get("page_number"))
        expected_type = _optional_str(expected.get("statement_type"))
        check_id = f"statement_page_{page_number or 'unknown'}"

        if page_number is None or expected_type is None:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message="Expected statement page requires page_number and statement_type.",
                )
            )
            continue

        actual = matches_by_page.get(page_number)
        if actual is None:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message=f"Page {page_number} is missing from statement classifications.",
                )
            )
            continue

        actual_type = _optional_str(actual.get("statement_type"))
        if actual_type == expected_type:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.PASS,
                    message=f"Page {page_number} classified as {actual_type}.",
                )
            )
        else:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message=(
                        f"Page {page_number} statement_type mismatch: "
                        f"expected {expected_type}, found {actual_type}."
                    ),
                )
            )

    return checks


def _validate_expected_metrics(
    gold_label: dict[str, object],
    analysis_json: dict[str, object],
) -> list[GoldLabelValidationCheck]:
    checks: list[GoldLabelValidationCheck] = []
    metric_results = _as_list(
        analysis_json.get("aggregated_metric_results")
        or analysis_json.get("aggregated_metrics")
    )
    metrics_by_name = {
        metric_name: metric
        for metric in metric_results
        if isinstance(metric, dict)
        and (metric_name := _metric_name_from_aggregated_result(metric)) is not None
    }

    for expected in _as_list(gold_label.get("expected_metrics")):
        if not isinstance(expected, dict):
            checks.append(
                GoldLabelValidationCheck(
                    check_id="metric_invalid",
                    status=GoldLabelValidationStatus.FAIL,
                    message="Expected metric entry must be an object.",
                )
            )
            continue

        metric_name = _optional_str(expected.get("metric_name"))
        check_id = f"metric_{metric_name or 'unknown'}"
        if metric_name is None:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message="Expected metric requires metric_name.",
                )
            )
            continue

        actual = metrics_by_name.get(metric_name)
        if actual is None:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message=f"Expected metric {metric_name} is missing.",
                )
            )
            continue

        metric_failures = _metric_value_failures(expected, actual)
        if metric_failures:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message=f"Metric {metric_name} failed: " + "; ".join(metric_failures),
                )
            )
        else:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.PASS,
                    message=f"Metric {metric_name} matched expected values.",
                )
            )

    return checks


def _validate_expected_scorecard(
    gold_label: dict[str, object],
    analysis_json: dict[str, object],
) -> list[GoldLabelValidationCheck]:
    expected_scorecard = gold_label.get("expected_scorecard")
    if expected_scorecard is None:
        return []
    if not isinstance(expected_scorecard, dict):
        return [
            GoldLabelValidationCheck(
                check_id="scorecard_expected",
                status=GoldLabelValidationStatus.FAIL,
                message="expected_scorecard must be an object when supplied.",
            )
        ]

    actual_scorecard = _scorecard_from_analysis(analysis_json)
    if actual_scorecard is None:
        return [
            GoldLabelValidationCheck(
                check_id="scorecard_present",
                status=GoldLabelValidationStatus.FAIL,
                message="Expected scorecard is present in gold label, but analysis scorecard is missing.",
            )
        ]

    checks: list[GoldLabelValidationCheck] = []
    for field_name, expected_value in expected_scorecard.items():
        check_id = f"scorecard_{field_name}"
        actual_value = actual_scorecard.get(field_name)
        if actual_value == expected_value:
            status = GoldLabelValidationStatus.PASS
            message = f"Scorecard {field_name} matched expected value {expected_value!r}."
            if field_name == "manual_review_required" and expected_value is True:
                status = GoldLabelValidationStatus.MANUAL_REVIEW
                message = "Scorecard manual_review_required=true matched expected manual review."
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=status,
                    message=message,
                )
            )
        else:
            checks.append(
                GoldLabelValidationCheck(
                    check_id=check_id,
                    status=GoldLabelValidationStatus.FAIL,
                    message=(
                        f"Scorecard {field_name} mismatch: "
                        f"expected {expected_value!r}, found {actual_value!r}."
                    ),
                )
            )

    return checks


def _metric_value_failures(
    expected: dict[str, object],
    actual: dict[str, object],
) -> list[str]:
    failures: list[str] = []
    tolerance = _optional_float(expected.get("tolerance"))
    if tolerance is None:
        tolerance = 0.0

    current_expected = _optional_float(expected.get("current_value"))
    if current_expected is not None:
        current_actual = _metric_current_value(actual)
        if current_actual is None:
            failures.append("current_value is missing from analysis metric")
        elif not _within_tolerance(current_actual, current_expected, tolerance):
            failures.append(
                f"current_value expected {current_expected}, found {current_actual}, tolerance {tolerance}"
            )

    previous_expected = _optional_float(expected.get("previous_value"))
    if previous_expected is not None:
        previous_actual = _metric_previous_value(actual)
        if previous_actual is None:
            failures.append("previous_value is missing from analysis metric")
        elif not _within_tolerance(previous_actual, previous_expected, tolerance):
            failures.append(
                f"previous_value expected {previous_expected}, found {previous_actual}, tolerance {tolerance}"
            )

    calculated_expected = _optional_float(expected.get("calculated_value"))
    if calculated_expected is not None:
        calculated_actual = _metric_calculated_value(actual)
        if calculated_actual is None:
            failures.append("calculated_value is missing from analysis metric")
        elif not _within_tolerance(calculated_actual, calculated_expected, tolerance):
            failures.append(
                f"calculated_value expected {calculated_expected}, found {calculated_actual}, tolerance {tolerance}"
            )

    reported_expected = _optional_float(expected.get("reported_value_optional"))
    if reported_expected is not None:
        reported_actual = _metric_reported_value(actual)
        if reported_actual is not None and not _within_tolerance(
            reported_actual,
            reported_expected,
            tolerance,
        ):
            failures.append(
                f"reported_value_optional expected {reported_expected}, found {reported_actual}, tolerance {tolerance}"
            )

    conflict_expected = expected.get("conflict_expected")
    if isinstance(conflict_expected, bool):
        conflict_actual = bool(actual.get("conflict", False))
        if conflict_actual is not conflict_expected:
            failures.append(
                f"conflict_expected expected {conflict_expected}, found {conflict_actual}"
            )

    return failures


def _metric_name_from_aggregated_result(metric: dict[str, object]) -> str | None:
    metric_name = _optional_str(metric.get("metric_name"))
    if metric_name is not None:
        return metric_name
    selected_metric = metric.get("selected_metric")
    if isinstance(selected_metric, dict):
        return _optional_str(selected_metric.get("metric_name"))
    return None


def _metric_current_value(metric: dict[str, object]) -> float | None:
    direct = _optional_float(metric.get("current_value"))
    if direct is not None:
        return direct
    selected_audit = _as_dict(metric.get("selected_audit_entry"))
    inputs = _as_dict(selected_audit.get("inputs")) if selected_audit else {}
    return _optional_float(inputs.get("current"))


def _metric_previous_value(metric: dict[str, object]) -> float | None:
    direct = _optional_float(metric.get("previous_value"))
    if direct is not None:
        return direct
    selected_audit = _as_dict(metric.get("selected_audit_entry"))
    inputs = _as_dict(selected_audit.get("inputs")) if selected_audit else {}
    return _optional_float(inputs.get("previous"))


def _metric_calculated_value(metric: dict[str, object]) -> float | None:
    direct = _optional_float(metric.get("calculated_value"))
    if direct is not None:
        return direct
    selected_metric = _as_dict(metric.get("selected_metric"))
    selected_value = _optional_float(selected_metric.get("value")) if selected_metric else None
    if selected_value is not None:
        return selected_value
    selected_audit = _as_dict(metric.get("selected_audit_entry"))
    if selected_audit:
        return _optional_float(selected_audit.get("output"))
    return None


def _metric_reported_value(metric: dict[str, object]) -> float | None:
    direct = _optional_float(metric.get("reported_value_optional"))
    if direct is not None:
        return direct
    occurrences = _as_list(metric.get("occurrences"))
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            continue
        reported = _optional_float(occurrence.get("reported_change_percent"))
        if reported is not None:
            return reported
    return None


def _scorecard_from_analysis(analysis_json: dict[str, object]) -> dict[str, object] | None:
    scorecard_build_result = analysis_json.get("scorecard_build_result")
    if isinstance(scorecard_build_result, dict):
        scorecard = scorecard_build_result.get("scorecard")
        if isinstance(scorecard, dict):
            return scorecard
    scorecard = analysis_json.get("fundamental_scorecard")
    if isinstance(scorecard, dict):
        return scorecard
    return None


def _within_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
