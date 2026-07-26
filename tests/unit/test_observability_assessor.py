"""Unit tests for ObservabilityAssessor — deterministic scoring and gate logic."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors.observability import ObservabilityAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import ObservabilitySourceReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _assessor(data: dict) -> ObservabilityAssessor:
    """Build an ObservabilityAssessor backed by an in-memory dict fixture."""
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(data, fh)
        path = Path(fh.name)

    return ObservabilityAssessor(
        ToolRunner(), RuleBasedProvider(), ObservabilitySourceReader(path=path)
    )


def _run(data: dict):
    return _assessor(data).assess()


# --- dimension identity ------------------------------------------------------------------


def test_dimension_name_is_observability() -> None:
    a = _assessor({})
    assert a.dimension is DimensionName.OBSERVABILITY


# --- score computation -------------------------------------------------------------------


def test_full_coverage_scores_1() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 100.0,
            "trace_coverage_pct": 100.0,
            "log_coverage_pct": 100.0,
            "runbooks_linked_to_alerts_pct": 100.0,
        }
    )
    assert result.available
    # score = 1.0*0.35 + 1.0*0.25 + 1.0*0.25 + 1.0*0.15 = 1.0
    assert abs(result.score - 1.0) < 1e-6


def test_zero_coverage_scores_0() -> None:
    result = _run(
        {
            "dashboards_configured": False,
            "slo_defined": False,
            "slo_alerts_configured": False,
            "alert_coverage_pct": 0.0,
            "trace_coverage_pct": 0.0,
            "log_coverage_pct": 0.0,
            "runbooks_linked_to_alerts_pct": 0.0,
        }
    )
    assert result.available
    assert abs(result.score - 0.0) < 1e-6


def test_partial_alert_coverage_partial_score() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 50.0,   # 0.5 contribution
            "trace_coverage_pct": 100.0,
            "log_coverage_pct": 100.0,
            "runbooks_linked_to_alerts_pct": 100.0,
        }
    )
    # score = 0.5*0.35 + 1.0*0.25 + 1.0*0.25 + 1.0*0.15 = 0.175 + 0.25 + 0.25 + 0.15 = 0.825
    assert result.available
    assert abs(result.score - 0.825) < 0.01


# --- gate / risk-factor logic ------------------------------------------------------------


def test_no_dashboards_emits_major_risk_factor() -> None:
    result = _run(
        {
            "dashboards_configured": False,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 100.0,
            "trace_coverage_pct": 100.0,
            "log_coverage_pct": 100.0,
            "runbooks_linked_to_alerts_pct": 100.0,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("dashboard" in rf.description.lower() for rf in majors)


def test_no_slo_emits_major_risk_factor() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": False,
            "slo_alerts_configured": False,
            "alert_coverage_pct": 80.0,
            "trace_coverage_pct": 70.0,
            "log_coverage_pct": 90.0,
            "runbooks_linked_to_alerts_pct": 75.0,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("service level objectives" in rf.description.lower() for rf in majors)


def test_slo_without_alerts_emits_major_risk_factor() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": False,
            "alert_coverage_pct": 80.0,
            "trace_coverage_pct": 70.0,
            "log_coverage_pct": 90.0,
            "runbooks_linked_to_alerts_pct": 75.0,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("alert" in rf.description.lower() for rf in majors)


def test_low_alert_coverage_emits_minor_risk_factor() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 30.0,  # below 50
            "trace_coverage_pct": 80.0,
            "log_coverage_pct": 80.0,
            "runbooks_linked_to_alerts_pct": 80.0,
        }
    )
    minors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert any("alert" in rf.description.lower() for rf in minors)


def test_low_trace_coverage_emits_minor_risk_factor() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 80.0,
            "trace_coverage_pct": 20.0,  # below 50
            "log_coverage_pct": 80.0,
            "runbooks_linked_to_alerts_pct": 80.0,
        }
    )
    minors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert any("trace" in rf.description.lower() for rf in minors)


def test_full_coverage_no_risk_factors() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 100.0,
            "trace_coverage_pct": 100.0,
            "log_coverage_pct": 100.0,
            "runbooks_linked_to_alerts_pct": 100.0,
        }
    )
    assert result.risk_factors == []


# --- confidence cap ----------------------------------------------------------------------


def test_no_slo_defined_applies_confidence_cap() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": False,
            "alert_coverage_pct": 80.0,
        }
    )
    assert result.confidence <= 0.75


def test_slo_defined_no_confidence_cap() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 80.0,
            "trace_coverage_pct": 70.0,
            "log_coverage_pct": 90.0,
            "runbooks_linked_to_alerts_pct": 75.0,
        }
    )
    assert result.confidence > 0.75


# --- classification ----------------------------------------------------------------------


def test_classification_poor_when_no_slo_and_no_dashboards() -> None:
    result = _run(
        {
            "dashboards_configured": False,
            "slo_defined": False,
        }
    )
    assert result.classification == "poor"


def test_classification_good_when_fully_configured() -> None:
    result = _run(
        {
            "dashboards_configured": True,
            "slo_defined": True,
            "slo_alerts_configured": True,
            "alert_coverage_pct": 100.0,
            "trace_coverage_pct": 100.0,
            "log_coverage_pct": 100.0,
            "runbooks_linked_to_alerts_pct": 100.0,
        }
    )
    assert result.classification == "good"
