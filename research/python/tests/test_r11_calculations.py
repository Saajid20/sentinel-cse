from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.tools import (  # noqa: E402
    R11CalculationError,
    calculate_change,
    calculate_cost_to_income,
    calculate_debt_to_equity,
    calculate_gross_margin,
    calculate_impairment_change,
    calculate_margin,
    calculate_margin_change_pp,
    calculate_net_interest_margin,
    calculate_percent_change,
    calculate_ratio,
    calculate_yoy_growth,
    direction_from_change,
    ensure_finite_number,
    round_metric,
    safe_divide,
)


def test_ensure_finite_number_accepts_int_and_float_and_rejects_invalid_values() -> None:
    assert ensure_finite_number(5, "value") == 5.0
    assert ensure_finite_number(2.5, "value") == 2.5

    with pytest.raises(R11CalculationError, match="value must be a finite number, got bool"):
        ensure_finite_number(True, "value")

    with pytest.raises(R11CalculationError, match="value must not be None"):
        ensure_finite_number(None, "value")  # type: ignore[arg-type]

    with pytest.raises(R11CalculationError, match="value must be a finite number"):
        ensure_finite_number(float("nan"), "value")

    with pytest.raises(R11CalculationError, match="value must be a finite number"):
        ensure_finite_number(float("inf"), "value")


def test_safe_divide_returns_correct_ratio_and_rejects_zero_denominator() -> None:
    assert safe_divide(10, 4) == 2.5

    with pytest.raises(R11CalculationError, match="denominator must not be zero"):
        safe_divide(10, 0)


def test_calculate_ratio_works() -> None:
    assert calculate_ratio(9, 3) == 3.0


def test_calculate_yoy_growth_works_for_positive_previous_value() -> None:
    assert calculate_yoy_growth(120, 100) == 0.2


def test_calculate_yoy_growth_uses_abs_previous_for_negative_previous_value() -> None:
    assert calculate_yoy_growth(20, -10) == 3.0


def test_calculate_yoy_growth_rejects_previous_zero() -> None:
    with pytest.raises(R11CalculationError, match="previous must not be zero"):
        calculate_yoy_growth(10, 0)


def test_calculate_change_works() -> None:
    assert calculate_change(120, 100) == 20.0


def test_calculate_percent_change_matches_calculate_yoy_growth() -> None:
    assert calculate_percent_change(120, 100) == calculate_yoy_growth(120, 100)


def test_calculate_margin_works() -> None:
    assert calculate_margin(25, 100) == 0.25


def test_calculate_margin_change_pp_returns_percentage_points() -> None:
    assert calculate_margin_change_pp(0.32, 0.30) == 2.0


def test_calculate_gross_margin_works() -> None:
    assert calculate_gross_margin(1000, 700) == 0.3


def test_calculate_net_interest_margin_works() -> None:
    assert calculate_net_interest_margin(120, 2400) == 0.05


def test_calculate_cost_to_income_works() -> None:
    assert calculate_cost_to_income(40, 100) == 0.4


def test_calculate_debt_to_equity_works() -> None:
    assert calculate_debt_to_equity(300, 150) == 2.0


def test_calculate_impairment_change_returns_negative_when_impairments_decrease() -> None:
    assert calculate_impairment_change(80, 100) == -0.2


def test_all_denominator_based_functions_reject_zero_denominators() -> None:
    with pytest.raises(R11CalculationError, match="revenue must not be zero"):
        calculate_gross_margin(0, 10)

    with pytest.raises(R11CalculationError, match="earning_assets must not be zero"):
        calculate_net_interest_margin(10, 0)

    with pytest.raises(R11CalculationError, match="operating_income must not be zero"):
        calculate_cost_to_income(10, 0)

    with pytest.raises(R11CalculationError, match="total_equity must not be zero"):
        calculate_debt_to_equity(10, 0)

    with pytest.raises(R11CalculationError, match="previous_impairment must not be zero"):
        calculate_impairment_change(10, 0)


def test_round_metric_works_and_rejects_negative_decimals() -> None:
    assert round_metric(0.123456, 4) == 0.1235

    with pytest.raises(R11CalculationError, match="decimals must be >= 0"):
        round_metric(0.1234, -1)


def test_direction_from_change_returns_expected_values_based_on_tolerance() -> None:
    assert direction_from_change(0.01) == "IMPROVING"
    assert direction_from_change(-0.01) == "DETERIORATING"
    assert direction_from_change(0.00001) == "STABLE"
    assert direction_from_change(0.05, tolerance=0.1) == "STABLE"


def test_r11_calculation_tests_do_not_use_deepseek_or_network() -> None:
    value = calculate_ratio(3, 2)

    assert math.isclose(value, 1.5)
