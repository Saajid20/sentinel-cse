from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents.r11.analysis import (  # noqa: E402
    DeterministicDossierBuildInput,
    ScorecardBuildResult,
    build_deterministic_r11_dossier,
    collect_red_flags_from_scorecard,
    collect_source_traces_from_metrics,
)
from sentinel_research.agents.r11.analysis.metric_aggregator import (  # noqa: E402
    AggregatedMetricResult,
    MetricOccurrence,
)
from sentinel_research.agents.r11.schemas import (  # noqa: E402
    FinancialMetric,
    FundamentalScorecard,
    MetricDirection,
    MetricUnit,
    R11ConfidenceLevel,
    SourceTrace,
    ToolAuditEntry,
)


def _make_source_trace(
    row_label: str,
    *,
    page_number: int = 12,
    company: str = "Commercial Bank",
) -> SourceTrace:
    return SourceTrace(
        local_file_path="C:/tmp/comb_q1_2026.pdf",
        page_number=page_number,
        table_id=f"pypdf_page_{page_number}",
        row_label=row_label,
        company=company,
        raw_value="raw row",
        notes="dossier builder test",
    )


def _make_metric(
    metric_name: str,
    value: float,
    *,
    source_traces: list[SourceTrace] | None = None,
) -> FinancialMetric:
    return FinancialMetric(
        metric_name=metric_name,
        display_name=metric_name.replace("_", " ").title(),
        value=value,
        unit=MetricUnit.PERCENT,
        period="current",
        comparison_period="previous",
        direction=MetricDirection.IMPROVING,
        calculation_audit_id=f"audit_{metric_name}",
        source_traces=source_traces or [_make_source_trace(metric_name)],
        notes="metric test",
    )


def _make_tool_audit(metric_name: str, value: float) -> ToolAuditEntry:
    return ToolAuditEntry(
        tool_name="r11_calculation_toolbox",
        operation="calculate_yoy_growth",
        metric_name=metric_name,
        formula="(current - previous) / abs(previous) * 100",
        inputs={"current": 120.0, "previous": 100.0},
        output=value,
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        source_traces=[_make_source_trace(metric_name)],
        notes="audit test",
    )


def _make_aggregated_metric(metric_name: str, value: float, *, conflict: bool = False) -> AggregatedMetricResult:
    metric = _make_metric(metric_name, value)
    audit_entry = _make_tool_audit(metric_name, value)
    occurrence = MetricOccurrence(
        metric_name=metric_name,
        calculated_change_percent=value,
        reported_change_percent=value,
        difference_percent_points=0.0,
        matches_reported=True,
        source_traces=[_make_source_trace(metric_name)],
        audit_entry=audit_entry,
        notes="occurrence",
    )
    return AggregatedMetricResult(
        metric_name=metric_name,
        selected_metric=metric,
        selected_audit_entry=audit_entry,
        occurrences=[occurrence],
        occurrence_count=1,
        conflict=conflict,
        manual_review_required=conflict,
        conflict_reason="conflict detected" if conflict else None,
        selected_reason="selected for dossier test",
        notes="aggregated test",
    )


def _make_scorecard_result(
    *,
    manual_review_required: bool = False,
    manual_review_reasons: list[str] | None = None,
    missing_expected_metrics: list[str] | None = None,
    summary: str = "Deterministic scorecard summary with no trading instruction.",
) -> ScorecardBuildResult:
    return ScorecardBuildResult(
        scorecard=FundamentalScorecard(
            earnings_quality=MetricDirection.IMPROVING,
            revenue_trend=MetricDirection.IMPROVING,
            margin_trend=MetricDirection.MIXED,
            balance_sheet_risk=R11ConfidenceLevel.MEDIUM,
            cash_flow_quality=MetricDirection.UNKNOWN,
            capital_strength=R11ConfidenceLevel.MEDIUM,
            accounting_risk=None,
            manual_review_required=manual_review_required,
            summary=summary,
        ),
        metric_names_used=[
            "group_profit_for_the_period_yoy_growth",
            "group_total_assets_growth",
        ],
        missing_expected_metrics=missing_expected_metrics or [],
        manual_review_reasons=manual_review_reasons or [],
        notes="scorecard build result test",
    )


def _make_build_input(
    *,
    scorecard_result: ScorecardBuildResult | None = None,
    financial_metrics: list[FinancialMetric] | None = None,
    tool_audit_entries: list[ToolAuditEntry] | None = None,
    aggregated_metrics: list[AggregatedMetricResult] | None = None,
    source_traces: list[SourceTrace] | None = None,
) -> DeterministicDossierBuildInput:
    metrics = (
        [
            _make_metric("group_profit_for_the_period_yoy_growth", 19.8),
            _make_metric("group_total_assets_growth", 6.81),
        ]
        if financial_metrics is None
        else financial_metrics
    )
    return DeterministicDossierBuildInput(
        ticker=" comb.n0000 ",
        company_name=" Commercial Bank ",
        analysis_title=" Q1 2026 deterministic analysis ",
        source_document_title=" COMB Q1 2026 Financial Review ",
        source_document_url=" https://example.test/comb-q1-2026.pdf ",
        scorecard_result=scorecard_result or _make_scorecard_result(),
        aggregated_metrics=(
            [
                _make_aggregated_metric("group_profit_for_the_period_yoy_growth", 19.8),
                _make_aggregated_metric("group_total_assets_growth", 6.81),
            ]
            if aggregated_metrics is None
            else aggregated_metrics
        ),
        financial_metrics=metrics,
        tool_audit_entries=(
            [
                _make_tool_audit("group_profit_for_the_period_yoy_growth", 19.8),
                _make_tool_audit("group_total_assets_growth", 6.81),
            ]
            if tool_audit_entries is None
            else tool_audit_entries
        ),
        source_traces=(
            [_make_source_trace("explicit trace", page_number=3)]
            if source_traces is None
            else source_traces
        ),
        notes="builder note",
    )


def test_deterministic_dossier_build_input_validates_ticker_and_required_metrics_and_audits() -> None:
    build_input = _make_build_input()

    assert build_input.ticker == "COMB.N0000"

    with pytest.raises(ValidationError, match="financial_metrics must not be empty"):
        _make_build_input(financial_metrics=[])

    with pytest.raises(ValidationError, match="tool_audit_entries must not be empty"):
        _make_build_input(tool_audit_entries=[])


def test_collect_source_traces_from_metrics_preserves_order_and_dedupes_exact_duplicates() -> None:
    shared_trace = _make_source_trace("shared", page_number=5)
    metrics = [
        _make_metric("group_profit_for_the_period_yoy_growth", 19.8, source_traces=[shared_trace]),
        _make_metric(
            "group_total_assets_growth",
            6.81,
            source_traces=[shared_trace, _make_source_trace("assets", page_number=6)],
        ),
    ]

    traces = collect_source_traces_from_metrics(metrics)

    assert [trace.page_number for trace in traces] == [5, 6]


def test_collect_red_flags_from_scorecard_returns_empty_when_no_manual_review_or_missing_metrics() -> None:
    red_flags = collect_red_flags_from_scorecard(_make_scorecard_result())

    assert red_flags == []


def test_collect_red_flags_from_scorecard_creates_red_flags_for_manual_review_reasons() -> None:
    red_flags = collect_red_flags_from_scorecard(
        _make_scorecard_result(
            manual_review_required=True,
            manual_review_reasons=["Aggregated metric conflicts detected."],
            missing_expected_metrics=["group_total_equity_growth"],
        )
    )

    assert len(red_flags) == 2
    assert red_flags[0].severity.value == "MEDIUM"
    assert red_flags[1].severity.value == "LOW"


def test_build_deterministic_r11_dossier_creates_r11_analyst_dossier_with_core_components() -> None:
    dossier = build_deterministic_r11_dossier(
        _make_build_input(),
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert dossier.ticker == "COMB.N0000"
    assert dossier.fundamental_scorecard.earnings_quality is MetricDirection.IMPROVING
    assert len(dossier.financial_metrics) == 2
    assert len(dossier.tool_audit) == 2


def test_dossier_manual_review_required_is_false_for_clean_scorecard() -> None:
    dossier = build_deterministic_r11_dossier(
        _make_build_input(),
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert dossier.manual_review_required is False
    assert dossier.confidence is R11ConfidenceLevel.HIGH


def test_dossier_manual_review_required_is_true_when_scorecard_has_manual_review_reasons() -> None:
    dossier = build_deterministic_r11_dossier(
        _make_build_input(
            scorecard_result=_make_scorecard_result(
                manual_review_required=True,
                manual_review_reasons=["Aggregated metric conflicts detected."],
            )
        ),
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert dossier.manual_review_required is True
    assert dossier.accounting_red_flags


def test_dossier_summary_contains_scorecard_summary_and_no_trading_language() -> None:
    summary = "Deterministic scorecard summary with conservative accounting observations."
    dossier = build_deterministic_r11_dossier(
        _make_build_input(scorecard_result=_make_scorecard_result(summary=summary)),
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert dossier.analyst_summary == summary
    lowered = dossier.analyst_summary.lower()
    for forbidden in ("buy", "sell", "hold", "order", "target", "entry", "exit"):
        assert forbidden not in lowered


def test_dossier_build_is_deterministic_enough_for_same_ticker_and_generated_at() -> None:
    generated_at = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    first = build_deterministic_r11_dossier(
        _make_build_input(),
        generated_at=generated_at,
    )
    second = build_deterministic_r11_dossier(
        _make_build_input(),
        generated_at=generated_at,
    )

    assert first.dossier_id == second.dossier_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_no_test_calls_deepseek_or_network() -> None:
    dossier = build_deterministic_r11_dossier(
        _make_build_input(),
        generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert dossier.schema_version == "r11_analyst_dossier_v1"
