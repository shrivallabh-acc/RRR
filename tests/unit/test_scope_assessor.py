"""Tests for ScopeAssessor (FR-1) against the real golden fixtures."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors import ScopeAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import RKTBrainReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_BRAIN = GOLDEN / "g1_clean_release" / "inputs" / "brain"
G5_BRAIN = GOLDEN / "g5_scope_creep" / "inputs" / "brain"
VS = "Retirement-Services"


def _assessor(brain_dir: Path, ir_name: str) -> ScopeAssessor:
    return ScopeAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        RKTBrainReader(brain_dir),
        value_stream=VS,
        ir_name=ir_name,
    )


def test_g1_clean_release_is_delivered() -> None:
    result = _assessor(G1_BRAIN, "Launch 36 - Unified Onboarding").assess()
    assert result.dimension is DimensionName.SCOPE and result.available is True
    assert result.score == 230 / 240  # 0.9583…
    assert abs(result.score - 0.958) < 0.03  # matches g1 ideal.json dimension score
    assert result.classification == "delivered"
    assert result.confidence == 1.0
    # no scope creep in g1 (240 -> 240)
    assert not any("scope" in rf.description.lower() for rf in result.risk_factors)


def test_g1_records_completion_evidence_and_tool_invocation() -> None:
    result = _assessor(G1_BRAIN, "Launch 36 - Unified Onboarding").assess()
    labels = {e.label for e in result.evidence}
    assert "scope_completion" in labels
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "rkt_brain_reader"
    assert result.tool_invocations[0].success is True


def test_g5_detects_scope_creep_but_still_delivered() -> None:
    result = _assessor(G5_BRAIN, "Launch 40 - Onboarding Plus").assess()
    assert result.score == 245 / 260  # 0.942…
    assert result.classification == "delivered"
    creep = [rf for rf in result.risk_factors if "scope grew" in rf.description.lower()]
    assert len(creep) == 1 and creep[0].severity is RiskSeverity.MAJOR
    assert "30.0%" in creep[0].description  # 200 -> 260


def test_missing_release_makes_dimension_unavailable() -> None:
    result = _assessor(G1_BRAIN, "Launch 99 - Ghost").assess()
    assert result.available is False
    assert result.score == 0.0 and result.confidence == 0.0
    assert result.tool_invocations and result.tool_invocations[0].success is False


def test_classification_thresholds() -> None:
    assert ScopeAssessor._classify(0.90).value == "delivered"
    assert ScopeAssessor._classify(0.89).value == "partially_delivered"
    assert ScopeAssessor._classify(0.50).value == "partially_delivered"
    assert ScopeAssessor._classify(0.49).value == "not_delivered"
