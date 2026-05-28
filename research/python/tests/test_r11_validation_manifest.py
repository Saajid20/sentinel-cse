from __future__ import annotations

import json
import sys
from itertools import count
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.validation import (  # noqa: E402
    ExpectedStatementPage,
    R11ValidationCase,
    R11ValidationManifest,
    R11ValidationManifestError,
    load_validation_manifest,
    save_validation_manifest,
    validation_case_to_cli_args,
)

_TMP_COUNTER = count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    base_dir = PYTHON_ROOT / ".pytest_tmp_validate_manifest"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{request.node.name}_{next(_TMP_COUNTER)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_case(**overrides: object) -> R11ValidationCase:
    payload = {
        "case_id": " comb_q1_2026_known_good ",
        "ticker": " COMB.N0000 ",
        "company_name": " Commercial Bank of Ceylon PLC ",
        "description": " Known-good deterministic COMB validation case. ",
        "analysis_json_path": " research/python/.r11_runtime/analysis/comb_q1_2026.json ",
        "expected_pages": [
            {"page_number": 5, "statement_type": "INCOME_STATEMENT"},
            {"page_number": 7, "statement_type": "BALANCE_SHEET"},
        ],
        "min_verified_metrics": 10,
        "min_aggregated_metrics": 10,
        "expect_manual_review": False,
        "require_scorecard": True,
        "require_no_conflicts": True,
        "notes": " local-only runtime path ",
    }
    payload.update(overrides)
    return R11ValidationCase.model_validate(payload)


def make_manifest(**overrides: object) -> R11ValidationManifest:
    payload = {
        "schema_version": "r11_validation_manifest_v1",
        "cases": [make_case().model_dump(mode="json")],
        "notes": " multi-case validation plan ",
    }
    payload.update(overrides)
    return R11ValidationManifest.model_validate(payload)


def test_manifest_accepts_valid_case() -> None:
    case = make_case()
    manifest = make_manifest()

    assert case.case_id == "comb_q1_2026_known_good"
    assert case.analysis_json_path == "research/python/.r11_runtime/analysis/comb_q1_2026.json"
    assert manifest.schema_version == "r11_validation_manifest_v1"


def test_duplicate_case_id_fails() -> None:
    duplicated = make_case(case_id="comb_q1_2026_known_good")

    with pytest.raises(ValidationError, match="duplicate case_id: comb_q1_2026_known_good"):
        make_manifest(cases=[make_case().model_dump(mode="json"), duplicated.model_dump(mode="json")])


def test_invalid_schema_version_fails() -> None:
    with pytest.raises(ValidationError, match="r11_validation_manifest_v1"):
        make_manifest(schema_version="r11_validation_manifest_v2")


def test_negative_minimum_metric_count_fails() -> None:
    with pytest.raises(ValidationError, match="min_verified_metrics must be >= 0"):
        make_case(min_verified_metrics=-1)

    with pytest.raises(ValidationError, match="min_aggregated_metrics must be >= 0"):
        make_case(min_aggregated_metrics=-1)


def test_load_validation_manifest_loads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(make_manifest().model_dump_json(indent=2), encoding="utf-8", newline="\n")

    manifest = load_validation_manifest(path)

    assert manifest.cases[0].case_id == "comb_q1_2026_known_good"


def test_load_validation_manifest_loads_utf8_bom_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest_bom.json"
    path.write_text(
        make_manifest().model_dump_json(indent=2),
        encoding="utf-8-sig",
        newline="\n",
    )

    manifest = load_validation_manifest(path)

    assert manifest.schema_version == "r11_validation_manifest_v1"
    assert manifest.cases[0].case_id == "comb_q1_2026_known_good"


def test_load_validation_manifest_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing_manifest.json"

    with pytest.raises(R11ValidationManifestError, match="Validation manifest path does not exist"):
        load_validation_manifest(path)


def test_save_validation_manifest_writes_json(tmp_path: Path) -> None:
    manifest = make_manifest()
    path = tmp_path / "nested" / "manifest.json"

    save_validation_manifest(manifest, path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "r11_validation_manifest_v1"
    assert payload["cases"][0]["case_id"] == "comb_q1_2026_known_good"


def test_validation_case_to_cli_args_emits_expected_page_args_and_thresholds() -> None:
    args = validation_case_to_cli_args(make_case())

    assert args == [
        "--analysis-json",
        "research/python/.r11_runtime/analysis/comb_q1_2026.json",
        "--expect-page",
        "5:INCOME_STATEMENT",
        "--expect-page",
        "7:BALANCE_SHEET",
        "--min-verified-metrics",
        "10",
        "--min-aggregated-metrics",
        "10",
        "--expect-manual-review",
        "false",
        "--require-scorecard",
        "--require-no-conflicts",
    ]


def test_empty_optional_strings_normalize_to_none() -> None:
    case = make_case(
        ticker=" ",
        company_name=" ",
        description=" ",
        notes=" ",
    )
    manifest = make_manifest(notes=" ")

    assert case.ticker is None
    assert case.company_name is None
    assert case.description is None
    assert case.notes is None
    assert manifest.notes is None


def test_no_test_calls_deepseek_or_network() -> None:
    page = ExpectedStatementPage(page_number=12, statement_type="CASH_FLOW")
    case = make_case(expected_pages=[page.model_dump(mode="json")], require_no_conflicts=False)

    args = validation_case_to_cli_args(case)

    assert "--analysis-json" in args
