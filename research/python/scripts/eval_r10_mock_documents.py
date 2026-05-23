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


def _compare_case(case: dict, analysis) -> list[str]:
    expected = case["expected"]
    failures: list[str] = []

    for field_name in (
        "analysis_scope",
        "macro_risk_level",
        "sentiment",
        "signal_policy",
        "manual_review_required",
    ):
        actual_value = getattr(analysis, field_name)
        actual_text = getattr(actual_value, "value", actual_value)
        if actual_text != expected[field_name]:
            failures.append(
                f"{field_name} expected {expected[field_name]!r} got {actual_text!r}"
            )

    missing_tags = _subset_missing(
        expected["must_include_catalyst_tags"],
        analysis.catalyst_tags,
    )
    if missing_tags:
        failures.append(f"missing catalyst_tags {missing_tags}")

    missing_sectors = _subset_missing(
        expected["must_include_affected_sectors"],
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
