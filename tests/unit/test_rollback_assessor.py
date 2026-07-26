"""Unit tests for RollbackAssessor — deterministic scoring and gate logic."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors.rollback import RollbackAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import RollbackSourceReader, ToolRunner


def _assessor(data: dict) -> RollbackAssessor:
    """Build a RollbackAssessor backed by an in-memory dict fixture."""
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(data, fh)
        path = Path(fh.name)

    return RollbackAssessor(ToolRunner(), RuleBasedProvider(), RollbackSourceReader(path=path))


def _run(data: dict):
    return _assessor(data).assess()


# --- dimension identity ------------------------------------------------------------------


def test_dimension_name_is_rollback() -> None:
    a = _assessor({})
    assert a.dimension is DimensionName.ROLLBACK


# --- score computation -------------------------------------------------------------------


def test_documented_and_tested_scores_1() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": False,
        }
    )
    assert result.available
    # plan_score=1.0; test_score=1.0 → score = 1.0*0.6 + 1.0*0.4 = 1.0
    assert abs(result.score - 1.0) < 1e-6


def test_documented_but_untested_scores_06() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    assert result.available
    # plan_score=1.0; test_score=0.0 → score = 1.0*0.6 + 0.0*0.4 = 0.6
    assert abs(result.score - 0.6) < 1e-6


def test_partial_plan_tested_scores_07() -> None:
    result = _run(
        {
            "rollback_plan": "partial",
            "rollback_tested": True,
            "data_rollback_applicable": False,
        }
    )
    assert result.available
    # plan_score=0.5; test_score=1.0 → score = 0.5*0.6 + 1.0*0.4 = 0.7
    assert abs(result.score - 0.7) < 1e-6


def test_no_plan_scores_zero_plan_component() -> None:
    result = _run(
        {
            "rollback_plan": "none",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    assert result.available
    # plan_score=0.0; test_score=0.0 → score = 0.0*0.6 + 0.0*0.4 = 0.0
    assert abs(result.score - 0.0) < 1e-6


def test_unknown_plan_scores_partial() -> None:
    result = _run(
        {
            "rollback_plan": "unknown",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    assert result.available
    # plan_score=0.3; test_score=0.0 → score = 0.3*0.6 + 0.0*0.4 = 0.18
    assert abs(result.score - 0.18) < 0.01


# --- gate / risk-factor logic ------------------------------------------------------------


def test_no_plan_emits_critical_risk_factor() -> None:
    result = _run({"rollback_plan": "none", "data_rollback_applicable": False})
    criticals = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("rollback" in rf.description.lower() for rf in criticals)


def test_data_rollback_applicable_without_plan_emits_critical() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": True,
            "data_rollback_plan_exists": False,
        }
    )
    criticals = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("data" in rf.description.lower() for rf in criticals)


def test_data_rollback_with_plan_no_critical() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": True,
            "data_rollback_plan_exists": True,
        }
    )
    criticals = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    # data migration risk factor should NOT be critical when plan exists
    assert not any("data" in rf.description.lower() for rf in criticals)


def test_partial_plan_emits_major_risk_factor() -> None:
    result = _run(
        {
            "rollback_plan": "partial",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("partial" in rf.description.lower() for rf in majors)


def test_untested_documented_plan_emits_major_risk_factor() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    majors = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("test" in rf.description.lower() for rf in majors)


def test_fully_ready_no_risk_factors() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": False,
        }
    )
    assert result.risk_factors == []


# --- confidence cap ----------------------------------------------------------------------


def test_unknown_plan_applies_confidence_cap() -> None:
    result = _run({"rollback_plan": "unknown"})
    assert result.confidence <= 0.70


def test_documented_plan_no_confidence_cap() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": False,
        }
    )
    assert result.confidence > 0.70


# --- classification ----------------------------------------------------------------------


def test_classification_not_ready_when_no_plan() -> None:
    result = _run({"rollback_plan": "none", "data_rollback_applicable": False})
    assert result.classification == "not_ready"


def test_classification_not_ready_when_data_migration_unplanned() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": True,
            "data_rollback_plan_exists": False,
        }
    )
    assert result.classification == "not_ready"


def test_classification_at_risk_when_partial_or_untested() -> None:
    result = _run(
        {
            "rollback_plan": "partial",
            "rollback_tested": False,
            "data_rollback_applicable": False,
        }
    )
    assert result.classification == "at_risk"


def test_classification_ready_when_documented_and_tested() -> None:
    result = _run(
        {
            "rollback_plan": "documented",
            "rollback_tested": True,
            "data_rollback_applicable": False,
        }
    )
    assert result.classification == "ready"
