from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import ContextAgent, DeepSeekProvider, R10AnalysisError  # noqa: E402
from sentinel_research.agents.evals import load_mock_documents  # noqa: E402


def _subset_missing(required_values: list[str], actual_values: list[str]) -> list[str]:
    actual_set = {value.strip() for value in actual_values}
    return [value for value in required_values if value.strip() not in actual_set]


def _matches_any_alias_groups(alias_groups: list[list[str]], actual_values: list[str]) -> list[list[str]]:
    actual_set = {value.strip() for value in actual_values}
    return [group for group in alias_groups if not any(alias.strip() in actual_set for alias in group)]


def _actual_scalar_value(value):
    return getattr(value, "value", value)


def _compare_scalar(
    expected: dict,
    exact_key: str,
    any_of_key: str,
    actual_value,
    failures: list[str],
) -> None:
    actual_text = _actual_scalar_value(actual_value)
    if any_of_key in expected:
        allowed_values = expected[any_of_key]
        if actual_text not in allowed_values:
            failures.append(f"{exact_key} expected one of {allowed_values!r} got {actual_text!r}")
        return
    if actual_text != expected[exact_key]:
        failures.append(f"{exact_key} expected {expected[exact_key]!r} got {actual_text!r}")


def _compare_case(case: dict, analysis) -> list[str]:
    expected = case["expected"]
    failures: list[str] = []

    for field_name in ("analysis_scope", "macro_risk_level", "sentiment", "signal_policy"):
        _compare_scalar(
            expected,
            field_name,
            f"{field_name}_any_of",
            getattr(analysis, field_name),
            failures,
        )

    _compare_scalar(
        expected,
        "manual_review_required",
        "manual_review_required_any_of",
        analysis.manual_review_required,
        failures,
    )

    if "catalyst_tag_any_of_groups" in expected:
        missing_tag_groups = _matches_any_alias_groups(
            expected["catalyst_tag_any_of_groups"],
            analysis.catalyst_tags,
        )
        for group in missing_tag_groups:
            failures.append(
                f"expected catalyst concept aliases {group!r} but got actual tags {analysis.catalyst_tags!r}"
            )
    else:
        missing_tags = _subset_missing(
            expected.get("must_include_catalyst_tags", []),
            analysis.catalyst_tags,
        )
        if missing_tags:
            failures.append(f"missing catalyst_tags {missing_tags}")

    if "affected_sector_any_of_groups" in expected:
        missing_sector_groups = _matches_any_alias_groups(
            expected["affected_sector_any_of_groups"],
            analysis.affected_sectors,
        )
        for group in missing_sector_groups:
            failures.append(
                f"expected sector concept aliases {group!r} but got actual sectors {analysis.affected_sectors!r}"
            )
    else:
        missing_sectors = _subset_missing(
            expected.get("must_include_affected_sectors", []),
            analysis.affected_sectors,
        )
        if missing_sectors:
            failures.append(f"missing affected_sectors {missing_sectors}")

    return failures


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("R10 mock-document eval requires DEEPSEEK_API_KEY to be set in the environment.")
        return 1

    try:
        cases = load_mock_documents()
        provider = DeepSeekProvider(api_key=api_key)
        agent = ContextAgent(provider)
        passed = 0
        failed = 0

        for case in cases:
            sources = [
                {
                    "source_type": case["source_type"],
                    "title": case["title"],
                    "url": case["url"],
                    "published_at": case["published_at"],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
            try:
                analysis = agent.process_document(
                    document=case["document"],
                    sources=sources,
                )
            except R10AnalysisError as error:
                failed += 1
                print(f"FAIL {case['id']}: validation failed: {error}")
                continue

            failures = _compare_case(case, analysis)
            if failures:
                failed += 1
                print(f"FAIL {case['id']}: {'; '.join(failures)}")
                print(analysis.model_dump_json(indent=2))
                continue

            passed += 1
            print(
                f"PASS {case['id']}: "
                f"{analysis.analysis_scope.value} {analysis.sentiment.value} "
                f"{analysis.signal_policy.value}"
            )

        print(f"Total passed: {passed}")
        print(f"Total failed: {failed}")
        return 0 if failed == 0 else 2
    except Exception as error:
        print(f"R10 mock-document eval failed unexpectedly: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
