"""Unit tests for OperabilityAssessor — deterministic scoring and gate logic."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors.operability import OperabilityAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import OperabilitySourceReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def _assessor(data: dict) -> OperabilityAssessor:
    """Build an OperabilityAssessor backed by an in-memory dict fixture."""
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(data, fh)
        path = Path(fh.name)

    return OperabilityAssessor(
        ToolRunner(), RuleBasedProvider(), OperabilitySourceReader(path=path)
    )


def _run(data: dict):
    return _assessor(data).assess()


# --- dimension identity ------------------------------------------------------------------


def test_dimension_name_is_operability() -> None:
    a = _assessor({})
    assert a.dimension is DimensionName.OPERABILITY


# --- score computation -------------------------------------------------------------------


def test_green_pipeline_full_runbook_on_call_scores_1() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "change_freeze": False,
            "recent_deployment_failures": 0,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    assert result.available
    assert abs(result.score - 1.0) < 1e-6


def test_yellow_pipeline_lowers_score() -> None:
    result = _run(
        {
            "deployment_pipeline": "yellow",
            "change_freeze": False,
            "recent_deployment_failures": 0,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    assert result.available
    # yellow pipeline_score ~0.6; ops_readiness=1.0 → score = 0.6*0.6 + 1.0*0.4 = 0.76
    assert abs(result.score - 0.76) < 0.01


def test_missing_runbook_and_oncall_reduces_score() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "change_freeze": False,
            "recent_deployment_failures": 0,
            "runbook_complete": False,
            "on_call_schedule_active": False,
        }
    )
    assert result.available
    # pipeline_score=1.0; ops_readiness = mean(0,0) = 0.0 → score = 1.0*0.6 + 0.0*0.4 = 0.6
    assert abs(result.score - 0.6) < 0.01


def test_red_pipeline_scores_zero_pipeline_component() -> None:
    result = _run(
        {
            "deployment_pipeline": "red",
            "change_freeze": False,
            "recent_deployment_failures": 0,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    assert result.available
    # pipeline_score=0.0; ops_readiness=1.0 → score = 0.0*0.6 + 1.0*0.4 = 0.4
    assert abs(result.score - 0.4) < 0.01


# --- gate / risk-factor logic ------------------------------------------------------------


def test_change_freeze_emits_critical_risk_factor() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "change_freeze": True,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    criticals = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("freeze" in rf.description.lower() for rf in criticals)


def test_red_pipeline_emits_critical_risk_factor() -> None:
    result = _run({"deployment_pipeline": "red"})
    criticals = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("red" in rf.description.lower() for rf in criticals)


def test_yellow_pipeline_emits_major_risk_factor() -> None:
    result = _run({"deployment_pipeline": "yellow"})
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("yellow" in rf.description.lower() for rf in majors)


def test_incomplete_runbook_emits_major_risk_factor() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "runbook_complete": False,
            "on_call_schedule_active": True,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("runbook" in rf.description.lower() for rf in majors)


def test_no_on_call_emits_major_risk_factor() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "runbook_complete": True,
            "on_call_schedule_active": False,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any(
        "on-call" in rf.description.lower() or "on_call" in rf.description.lower()
        for rf in majors
    )


def test_recent_failures_emits_minor_risk_factor() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "recent_deployment_failures": 3,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    minors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert any("failure" in rf.description.lower() for rf in minors)


def test_no_failures_emits_no_minor_risk_for_failures() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "recent_deployment_failures": 0,
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    minors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert not any("failure" in rf.description.lower() for rf in minors)


# --- confidence cap ----------------------------------------------------------------------


def test_unknown_pipeline_applies_confidence_cap() -> None:
    result = _run({"deployment_pipeline": "unknown"})
    assert result.confidence <= 0.75


def test_green_pipeline_no_confidence_cap() -> None:
    result = _run(
        {
            "deployment_pipeline": "green",
            "runbook_complete": True,
            "on_call_schedule_active": True,
        }
    )
    # No cap should apply — confidence stays at or close to 1.0
    assert result.confidence > 0.75


# --- golden fixture integration ----------------------------------------------------------


def test_g1_operability_scores_1() -> None:
    path = GOLDEN / "g1_clean_release" / "inputs" / "operability.json"
    assessor = OperabilityAssessor(
        ToolRunner(), RuleBasedProvider(), OperabilitySourceReader(path=path)
    )
    result = assessor.assess()
    assert result.available
    assert abs(result.score - 1.0) < 0.03


def test_g2_operability_scores_around_076() -> None:
    path = GOLDEN / "g2_failing_tests" / "inputs" / "operability.json"
    assessor = OperabilityAssessor(
        ToolRunner(), RuleBasedProvider(), OperabilitySourceReader(path=path)
    )
    result = assessor.assess()
    assert result.available
    assert abs(result.score - 0.76) < 0.03
