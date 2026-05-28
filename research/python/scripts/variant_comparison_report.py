from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any


class VariantComparisonFormatError(ValueError):
    """Raised when an input file is not a strategy variant comparison JSON export."""


@dataclass(frozen=True)
class SignalTickerCount:
    ticker: str
    count: int | None


@dataclass(frozen=True)
class VariantSummary:
    variant_name: str | None
    diagnostic_only: bool | None
    description: str | None
    parameter_overrides: dict[str, Any]
    runtime_mode: str | None
    replayed_snapshots: int | None
    signals_generated: int | None
    unique_signal_tickers: int | None
    generated_strategies: list[str]
    signal_ticker_counts: list[SignalTickerCount]


@dataclass(frozen=True)
class BaselineDelta:
    variant_name: str | None
    delta_signals: int | None
    changed: bool


@dataclass(frozen=True)
class VariantComparisonReport:
    session_id: str | None
    input_path: str | None
    source: str | None
    total_snapshots_loaded: int | None
    unique_tickers: int | None
    top_signal_ticker_limit: int | None
    variant_count: int
    variants: list[VariantSummary]
    baseline_variant_name: str | None
    baseline_signal_count: int | None
    baseline_deltas: list[BaselineDelta] = field(default_factory=list)
    changed_variants: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    top_limit: int | None = None


def load_variant_comparison(path: str | Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise VariantComparisonFormatError(
            f"Unable to read variant comparison file: {path}. {error}"
        ) from error

    try:
        comparison = json.loads(raw)
    except json.JSONDecodeError as error:
        raise VariantComparisonFormatError(
            f"Malformed variant comparison JSON: {error}"
        ) from error

    validate_variant_comparison(comparison)
    return comparison


def validate_variant_comparison(comparison: Any) -> None:
    if not isinstance(comparison, dict):
        raise VariantComparisonFormatError("Variant comparison root must be an object.")


def build_variant_comparison_report(
    comparison: dict[str, Any],
    top: int | None = 10,
) -> VariantComparisonReport:
    variants = parse_variants(comparison.get("variants"))
    safe_top = max(top, 0) if top is not None else None
    baseline_variant = next(
        (variant for variant in variants if variant.variant_name == "baseline"),
        variants[0] if variants else None,
    )
    baseline_signal_count = baseline_variant.signals_generated if baseline_variant else None

    baseline_deltas: list[BaselineDelta] = []
    changed_variants: list[str] = []
    for variant in variants:
        delta = calculate_delta(variant.signals_generated, baseline_signal_count)
        changed = delta not in (None, 0)
        baseline_deltas.append(
            BaselineDelta(
                variant_name=variant.variant_name,
                delta_signals=delta,
                changed=changed,
            )
        )
        if changed and variant.variant_name is not None:
            changed_variants.append(variant.variant_name)

    warnings = [
        "offline research only; diagnostic variants are not production recommendations"
    ]
    warnings.extend(
        f"diagnostic-only variant {variant.variant_name} generated {variant.signals_generated} signals"
        for variant in variants
        if variant.diagnostic_only is True
        and variant.signals_generated is not None
        and variant.signals_generated > 0
        and variant.variant_name is not None
    )

    return VariantComparisonReport(
        session_id=optional_string(comparison.get("sessionId")),
        input_path=optional_string(comparison.get("inputPath")),
        source=optional_string(comparison.get("source")),
        total_snapshots_loaded=optional_int(comparison.get("totalSnapshotsLoaded")),
        unique_tickers=optional_int(comparison.get("uniqueTickers")),
        top_signal_ticker_limit=optional_int(comparison.get("topSignalTickerLimit")),
        variant_count=len(variants),
        variants=variants,
        baseline_variant_name=baseline_variant.variant_name if baseline_variant else None,
        baseline_signal_count=baseline_signal_count,
        baseline_deltas=baseline_deltas,
        changed_variants=changed_variants,
        warnings=warnings,
        top_limit=safe_top,
    )


def parse_variants(value: Any) -> list[VariantSummary]:
    if not isinstance(value, list):
        return []

    variants: list[VariantSummary] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        variants.append(
            VariantSummary(
                variant_name=optional_string(item.get("variantName")),
                diagnostic_only=optional_bool(item.get("diagnosticOnly")),
                description=optional_string(item.get("description")),
                parameter_overrides=optional_dict(item.get("parameterOverrides")),
                runtime_mode=optional_string(item.get("runtimeMode")),
                replayed_snapshots=optional_int(item.get("replayedSnapshots")),
                signals_generated=optional_int(item.get("signalsGenerated")),
                unique_signal_tickers=optional_int(item.get("uniqueSignalTickers")),
                generated_strategies=optional_string_items(item.get("generatedStrategies")),
                signal_ticker_counts=parse_signal_ticker_counts(item.get("signalTickerCounts")),
            )
        )
    return variants


def parse_signal_ticker_counts(value: Any) -> list[SignalTickerCount]:
    if not isinstance(value, list):
        return []

    rows: list[SignalTickerCount] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            SignalTickerCount(
                ticker=optional_string(item.get("ticker")) or "unavailable",
                count=optional_int(item.get("count")),
            )
        )
    return rows


def calculate_delta(value: int | None, baseline: int | None) -> int | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def format_variant_comparison_report(report: VariantComparisonReport) -> str:
    lines = [
        "Sentinel-CSE strategy variant comparison report",
        f"sessionId: {format_optional_string(report.session_id)}",
        f"inputPath: {format_optional_string(report.input_path)}",
        f"source: {format_optional_string(report.source)}",
        f"totalSnapshotsLoaded: {format_optional_number(report.total_snapshots_loaded)}",
        f"uniqueTickers: {format_optional_number(report.unique_tickers)}",
        f"topSignalTickerLimit: {format_optional_number(report.top_signal_ticker_limit)}",
        f"variantCount: {format_optional_number(report.variant_count)}",
        f"display top signalTickerCounts: {format_optional_number(report.top_limit)}",
        "",
        "Variant summary:",
    ]

    if report.variants:
        for variant in report.variants:
            lines.extend(
                [
                    f"variant: {format_optional_string(variant.variant_name)}",
                    f"- diagnosticOnly: {format_optional_bool(variant.diagnostic_only)}",
                    f"- signalsGenerated: {format_optional_number(variant.signals_generated)}",
                    f"- uniqueSignalTickers: {format_optional_number(variant.unique_signal_tickers)}",
                    f"- parameterOverrides: {format_parameter_overrides(variant.parameter_overrides)}",
                    f"- generatedStrategies: {format_string_list(variant.generated_strategies)}",
                    f"- top signalTickerCounts: {format_signal_ticker_counts(variant.signal_ticker_counts, report.top_limit)}",
                ]
            )
    else:
        lines.append("No variants found.")

    lines.extend(
        [
            "",
            "Baseline delta summary:",
            f"- baseline variant: {format_optional_string(report.baseline_variant_name)}",
            f"- baseline signalsGenerated: {format_optional_number(report.baseline_signal_count)}",
        ]
    )
    if report.baseline_deltas:
        lines.extend(
            f"- {format_optional_string(item.variant_name)}: {format_delta(item.delta_signals)}"
            + (" changed" if item.changed else " unchanged")
            for item in report.baseline_deltas
        )
    else:
        lines.append("- unavailable")
    lines.append(f"- changed variants: {format_string_list(report.changed_variants)}")

    lines.extend(["", "Warnings:"])
    lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines)


def optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            try:
                return int(stripped)
            except ValueError:
                return None
    return None


def optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def optional_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def optional_string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def format_optional_string(value: str | None) -> str:
    return value if value is not None else "unavailable"


def format_optional_number(value: int | None) -> str:
    if value is None:
        return "unavailable"
    return f"{value:,}"


def format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "unavailable"
    return "yes" if value else "no"


def format_parameter_overrides(value: dict[str, Any]) -> str:
    if not value:
        return "default"
    items = sorted(value.items(), key=lambda item: item[0])
    return ", ".join(f"{key}={format_parameter_value(raw)}" for key, raw in items)


def format_parameter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        decimal_value = Decimal(str(value))
        if decimal_value == decimal_value.quantize(Decimal("1")):
            return str(int(decimal_value))
        return format(decimal_value.normalize(), "f").rstrip("0").rstrip(".")
    return format_optional_string(optional_string(value))


def format_string_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


def format_signal_ticker_counts(values: list[SignalTickerCount], top: int | None) -> str:
    if not values or top == 0:
        return "none"
    sliced = values[:top] if top is not None else values
    return ", ".join(
        f"{item.ticker}:{format_optional_number(item.count)}" for item in sliced
    )


def format_delta(value: int | None) -> str:
    if value is None:
        return "unavailable"
    if value > 0:
        return f"+{value}"
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize one exported Sentinel-CSE strategy variant comparison JSON file."
    )
    parser.add_argument("--input", required=True, help="Path to a variant comparison JSON file.")
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of signalTickerCounts rows to display per variant.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        comparison = load_variant_comparison(Path(args.input))
        report = build_variant_comparison_report(comparison, top=max(args.top, 0))
        print(format_variant_comparison_report(report))
        return 0
    except VariantComparisonFormatError as error:
        print(f"Variant comparison report failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
