"""Tests for ProductionReadinessAssessor (ADR-0016 item 14, gate-only dimension).

Uses synthetic tmp_path stubs. Score is the mean of booleans, feature flags (None
treated as True), and stakeholder sign-offs as documented in the assessor module.
"""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.production_readiness import ProductionReadinessAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.production_readiness import ProductionReadinessInput
from rrr.providers import RuleBasedProvider
from rrr.tools import ProductionReadinessSourceReader, ToolRunner


def _assessor(path: Path) -> ProductionReadinessAssessor:
    return ProductionReadinessAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        ProductionReadinessSourceReader(path=str(path)),
    )


def _stub(tmp_path: Path, **fields: object) -> Path:
    """Write a minimal production_readiness.json stub, merging caller fields over a baseline."""
    base: dict[str, object] = {
        "capacity_confirmed": True,
        "feature_flags_configured": True,
        "go_live_checklist_complete": True,
        "stakeholder_sign_offs": {
            "product": True,
            "engineering": True,
            "security": True,
            "operations": True,
        },
        "release_comms_prepared": True,
        "support_team_briefed": True,
        "rollback_decision_criteria_defined": True,
        "post_release_monitoring_plan": True,
    }
    base.update(fields)
    p = tmp_path / "production_readiness.json"
    p.write_text(json.dumps(base))
    return p


# --- clean posture (all signals true) ------------------------------------------------------------


def test_clean_posture_score_is_one(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert result.dimension is DimensionName.PRODUCTION_READINESS
    assert result.available is True
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "ready"
    assert not result.risk_factors


def test_clean_posture_records_tool_invocation(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "production_readiness_source"
    assert result.tool_invocations[0].success is True


def test_clean_posture_evidence_label_present(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path)).assess()
    labels = {e.label for e in result.evidence}
    assert "production_readiness_score" in labels


# --- capacity_confirmed=False → CRITICAL ---------------------------------------------------------


def test_capacity_unconfirmed_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, capacity_confirmed=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("capacity" in rf.description.lower() for rf in critical)


def test_capacity_unconfirmed_classification_is_not_ready(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, capacity_confirmed=False)).assess()
    assert result.classification == "not_ready"


# --- go_live_checklist_complete=False → CRITICAL -------------------------------------------------


def test_checklist_incomplete_raises_critical(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, go_live_checklist_complete=False)).assess()
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("checklist" in rf.description.lower() for rf in critical)


def test_checklist_incomplete_classification_is_not_ready(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, go_live_checklist_complete=False)).assess()
    assert result.classification == "not_ready"


# --- stakeholder sign-off missing → MAJOR --------------------------------------------------------


def test_missing_signoff_raises_major(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            stakeholder_sign_offs={
                "product": True,
                "engineering": False,
                "security": True,
                "operations": True,
            },
        )
    ).assess()
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("sign-off" in rf.description.lower() for rf in major)


def test_missing_signoff_classification_is_at_risk(tmp_path: Path) -> None:
    result = _assessor(
        _stub(
            tmp_path,
            stakeholder_sign_offs={
                "product": True,
                "engineering": None,
            },
        )
    ).assess()
    assert result.classification == "at_risk"


# --- feature_flags_configured=None → treated as True (full credit) --------------------------------


def test_feature_flags_none_treated_as_not_applicable(tmp_path: Path) -> None:
    result = _assessor(_stub(tmp_path, feature_flags_configured=None)).assess()
    # flags_score = 1.0 when None → score stays 1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "ready"


# --- missing file → unavailable ------------------------------------------------------------------


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.dimension is DimensionName.PRODUCTION_READINESS


# --- _classify static method unit tests ----------------------------------------------------------


def test_classify_ready_when_all_confirmed_and_signed() -> None:
    data = ProductionReadinessInput(
        capacity_confirmed=True,
        go_live_checklist_complete=True,
        stakeholder_sign_offs={"product": True, "engineering": True},
    )
    assert ProductionReadinessAssessor._classify(data) == "ready"


def test_classify_not_ready_when_capacity_unconfirmed() -> None:
    data = ProductionReadinessInput(
        capacity_confirmed=False,
        go_live_checklist_complete=True,
        stakeholder_sign_offs={"product": True},
    )
    assert ProductionReadinessAssessor._classify(data) == "not_ready"


def test_classify_at_risk_when_signoff_pending() -> None:
    data = ProductionReadinessInput(
        capacity_confirmed=True,
        go_live_checklist_complete=True,
        stakeholder_sign_offs={"product": True, "security": None},
    )
    assert ProductionReadinessAssessor._classify(data) == "at_risk"
