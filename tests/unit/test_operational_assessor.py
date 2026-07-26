"""Tests for OperationalAssessor (ADR-0016) against golden fixtures and synthetic stubs."""

from __future__ import annotations

import json
from pathlib import Path

from rrr.assessors.operational import OperationalAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import OperationalSourceReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_OP = GOLDEN / "g1_clean_release" / "inputs" / "operational.json"
G5_OP = GOLDEN / "g5_scope_creep" / "inputs" / "operational.json"


def _assessor(path: Path) -> OperationalAssessor:
    return OperationalAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        OperationalSourceReader(path=str(path)),
    )


# --- golden fixture coverage -------------------------------------------------------------------


def test_g1_clean_pipeline_is_fully_ready() -> None:
    result = _assessor(G1_OP).assess()
    assert result.dimension is DimensionName.OPERATIONAL and result.available is True
    # pipeline=green (1.0) × 0.6 + rollback=documented (1.0) × 0.4 = 1.0
    assert abs(result.score - 1.0) < 0.001
    assert result.classification == "ready"
    assert result.confidence == 1.0
    assert not result.risk_factors


def test_g1_records_evidence_and_tool_invocation() -> None:
    result = _assessor(G1_OP).assess()
    labels = {e.label for e in result.evidence}
    assert "operational_score" in labels
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "operational_source"
    assert result.tool_invocations[0].success is True


def test_g5_degraded_pipeline_produces_major_risks() -> None:
    result = _assessor(G5_OP).assess()
    # pipeline=yellow (0.6) × 0.6 + rollback=none (0.0) × 0.4 = 0.36
    assert abs(result.score - 0.36) < 0.001
    # yellow pipeline + no rollback = at_risk (not_ready requires RED or change_freeze)
    assert result.classification == "at_risk"
    severities = {rf.severity for rf in result.risk_factors}
    assert RiskSeverity.MAJOR in severities
    descriptions = [rf.description for rf in result.risk_factors]
    assert any("yellow" in d.lower() for d in descriptions)
    assert any("rollback" in d.lower() for d in descriptions)
    # 2 failures → MINOR
    assert any("2 deployment failure" in d for d in descriptions)


# --- scoring math ------------------------------------------------------------------------------


def test_pipeline_red_scores_zero_and_critical_risk(tmp_path: Path) -> None:
    stub = tmp_path / "op.json"
    stub.write_text(
        json.dumps(
            {
                "deployment_pipeline": "red",
                "rollback_plan": "documented",
                "change_freeze": False,
                "recent_deployment_failures": 0,
            }
        )
    )
    result = _assessor(stub).assess()
    # pipeline=red (0.0) × 0.6 + rollback=documented (1.0) × 0.4 = 0.4
    assert abs(result.score - 0.4) < 0.001
    critical = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert len(critical) == 1 and "red" in critical[0].description.lower()


def test_change_freeze_produces_critical_risk(tmp_path: Path) -> None:
    stub = tmp_path / "op.json"
    stub.write_text(
        json.dumps(
            {
                "deployment_pipeline": "green",
                "rollback_plan": "documented",
                "change_freeze": True,
                "recent_deployment_failures": 0,
            }
        )
    )
    result = _assessor(stub).assess()
    # Freeze is CRITICAL regardless — score is still 1.0 (numeric) but gate caps verdict
    assert result.score == 1.0
    freeze_risks = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.CRITICAL]
    assert any("freeze" in rf.description.lower() for rf in freeze_risks)


def test_rollback_none_produces_major_risk(tmp_path: Path) -> None:
    stub = tmp_path / "op.json"
    stub.write_text(
        json.dumps(
            {
                "deployment_pipeline": "green",
                "rollback_plan": "none",
                "change_freeze": False,
                "recent_deployment_failures": 0,
            }
        )
    )
    result = _assessor(stub).assess()
    # pipeline=green (1.0) × 0.6 + rollback=none (0.0) × 0.4 = 0.6
    assert abs(result.score - 0.6) < 0.001
    major = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MAJOR]
    assert any("rollback" in rf.description.lower() for rf in major)


def test_deployment_failures_produce_minor_risk(tmp_path: Path) -> None:
    stub = tmp_path / "op.json"
    stub.write_text(
        json.dumps(
            {
                "deployment_pipeline": "green",
                "rollback_plan": "documented",
                "change_freeze": False,
                "recent_deployment_failures": 3,
            }
        )
    )
    result = _assessor(stub).assess()
    minor = [rf for rf in result.risk_factors if rf.severity is RiskSeverity.MINOR]
    assert len(minor) == 1 and "3 deployment failure" in minor[0].description


def test_unknown_pipeline_reduces_confidence(tmp_path: Path) -> None:
    stub = tmp_path / "op.json"
    stub.write_text(
        json.dumps(
            {
                "deployment_pipeline": "unknown",
                "rollback_plan": "documented",
                "change_freeze": False,
                "recent_deployment_failures": 0,
            }
        )
    )
    result = _assessor(stub).assess()
    # pipeline=unknown (0.5) × 0.6 + rollback=documented (1.0) × 0.4 = 0.7
    assert abs(result.score - 0.7) < 0.001
    # confidence capped at 0.75 when fields are unknown
    assert result.confidence <= 0.75


def test_missing_file_makes_dimension_unavailable(tmp_path: Path) -> None:
    result = _assessor(tmp_path / "nonexistent.json").assess()
    assert result.available is False
    assert result.score == 0.0 and result.confidence == 0.0
    assert result.tool_invocations and result.tool_invocations[0].success is False


# --- classification logic ----------------------------------------------------------------------


def test_classify_ready_requires_green_and_documented_and_no_freeze() -> None:
    from rrr.models.operational import OperationalInput

    ready = OperationalInput(
        deployment_pipeline="green", rollback_plan="documented", change_freeze=False
    )
    assert OperationalAssessor._classify(ready) == "ready"


def test_classify_at_risk_for_yellow_pipeline() -> None:
    from rrr.models.operational import OperationalInput

    at_risk = OperationalInput(
        deployment_pipeline="yellow", rollback_plan="documented", change_freeze=False
    )
    assert OperationalAssessor._classify(at_risk) == "at_risk"


def test_classify_not_ready_for_freeze() -> None:
    from rrr.models.operational import OperationalInput

    frozen = OperationalInput(
        deployment_pipeline="green", rollback_plan="documented", change_freeze=True
    )
    assert OperationalAssessor._classify(frozen) == "not_ready"
