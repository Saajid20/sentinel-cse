from __future__ import annotations

import math


class R11CalculationError(ValueError):
    """Raised when deterministic R11 metric inputs are invalid."""


def ensure_finite_number(value: int | float, name: str) -> float:
    if value is None:
        raise R11CalculationError(f"{name} must not be None")
    if isinstance(value, bool):
        raise R11CalculationError(f"{name} must be a finite number, got bool")
    if not isinstance(value, (int, float)):
        raise R11CalculationError(f"{name} must be a finite number")

    normalized = float(value)
    if not math.isfinite(normalized):
        raise R11CalculationError(f"{name} must be a finite number")
    return normalized


def safe_divide(
    numerator: int | float,
    denominator: int | float,
    *,
    numerator_name: str = "numerator",
    denominator_name: str = "denominator",
) -> float:
    normalized_numerator = ensure_finite_number(numerator, numerator_name)
    normalized_denominator = ensure_finite_number(denominator, denominator_name)

    if normalized_denominator == 0.0:
        raise R11CalculationError(f"{denominator_name} must not be zero")

    return normalized_numerator / normalized_denominator


def calculate_ratio(numerator: int | float, denominator: int | float) -> float:
    return safe_divide(numerator, denominator)


def calculate_yoy_growth(current: int | float, previous: int | float) -> float:
    normalized_current = ensure_finite_number(current, "current")
    normalized_previous = ensure_finite_number(previous, "previous")

    if normalized_previous == 0.0:
        raise R11CalculationError("previous must not be zero")

    return (normalized_current - normalized_previous) / abs(normalized_previous)


def calculate_change(current: int | float, previous: int | float) -> float:
    normalized_current = ensure_finite_number(current, "current")
    normalized_previous = ensure_finite_number(previous, "previous")
    return normalized_current - normalized_previous


def calculate_percent_change(current: int | float, previous: int | float) -> float:
    return calculate_yoy_growth(current, previous)


def calculate_margin(numerator: int | float, denominator: int | float) -> float:
    return safe_divide(numerator, denominator)


def calculate_margin_change_pp(
    current_margin: int | float,
    previous_margin: int | float,
) -> float:
    normalized_current = ensure_finite_number(current_margin, "current_margin")
    normalized_previous = ensure_finite_number(previous_margin, "previous_margin")
    return round((normalized_current - normalized_previous) * 100.0, 10)


def calculate_gross_margin(revenue: int | float, cost_of_sales: int | float) -> float:
    normalized_revenue = ensure_finite_number(revenue, "revenue")
    normalized_cost_of_sales = ensure_finite_number(cost_of_sales, "cost_of_sales")

    if normalized_revenue == 0.0:
        raise R11CalculationError("revenue must not be zero")

    return (normalized_revenue - normalized_cost_of_sales) / normalized_revenue


def calculate_net_interest_margin(
    net_interest_income: int | float,
    earning_assets: int | float,
) -> float:
    return safe_divide(
        net_interest_income,
        earning_assets,
        numerator_name="net_interest_income",
        denominator_name="earning_assets",
    )


def calculate_cost_to_income(
    operating_expenses: int | float,
    operating_income: int | float,
) -> float:
    return safe_divide(
        operating_expenses,
        operating_income,
        numerator_name="operating_expenses",
        denominator_name="operating_income",
    )


def calculate_debt_to_equity(total_debt: int | float, total_equity: int | float) -> float:
    return safe_divide(
        total_debt,
        total_equity,
        numerator_name="total_debt",
        denominator_name="total_equity",
    )


def calculate_impairment_change(
    current_impairment: int | float,
    previous_impairment: int | float,
) -> float:
    normalized_current = ensure_finite_number(current_impairment, "current_impairment")
    normalized_previous = ensure_finite_number(previous_impairment, "previous_impairment")

    if normalized_previous == 0.0:
        raise R11CalculationError("previous_impairment must not be zero")

    return (normalized_current - normalized_previous) / abs(normalized_previous)


def round_metric(value: float, decimals: int = 4) -> float:
    normalized_value = ensure_finite_number(value, "value")
    if decimals < 0:
        raise R11CalculationError("decimals must be >= 0")
    return round(normalized_value, decimals)


def direction_from_change(value: float, *, tolerance: float = 0.0001) -> str:
    normalized_value = ensure_finite_number(value, "value")
    normalized_tolerance = ensure_finite_number(tolerance, "tolerance")

    if normalized_tolerance < 0.0:
        raise R11CalculationError("tolerance must be >= 0")

    if normalized_value > normalized_tolerance:
        return "IMPROVING"
    if normalized_value < -normalized_tolerance:
        return "DETERIORATING"
    return "STABLE"
