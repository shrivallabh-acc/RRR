"""Tests for EstimationAssessor (FR-2) against the real golden fixtures."""

from __future__ import annotations

from pathlib import Path

from rrr.assessors import EstimationAssessor
from rrr.models.enums import DimensionName, EstimationClass, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import RKTBrainReader, ToolRunner

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_BRAIN = GOLDEN / "g1_clean_release" / "inputs" / "brain"
G5_BRAIN = GOLDEN / "g5_scope_creep" / "inputs" / "brain"
VS = "Retirement-Services"


def _assessor(brain_dir: Path, ir_name: str) -> EstimationAssessor:
    return EstimationAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        RKTBrainReader(brain_dir),
        value_stream=VS,
        ir_name=ir_name,
    )


def test_g1_within_tolerance() -> None:
    result = _assessor(G1_BRAIN, "Launch 36 - Unified Onboarding").assess()
    assert result.dimension is DimensionName.ESTIMATION and result.available is True
    assert abs(result.score - 0.990) < 0.03  # matches g1 ideal.json (var -1%)
    assert result.classification == "within_tolerance"
    assert result.confidence == 1.0
    assert result.risk_factors == []


def test_g5_over_estimated_out_of_tolerance() -> None:
    result = _assessor(G5_BRAIN, "Launch 40 - Onboarding Plus").assess()
    assert result.score == 0.80  # planned 200, actual 160 -> -20%
    assert result.classification == "over"
    assert len(result.risk_factors) == 1
    assert result.risk_factors[0].severity is RiskSeverity.MINOR


def test_missing_release_unavailable() -> None:
    result = _assessor(G1_BRAIN, "Launch 99 - Ghost").assess()
    assert result.available is False and result.score == 0.0 and result.confidence == 0.0


def test_classification_thresholds() -> None:
    a = _assessor(G1_BRAIN, "Launch 36 - Unified Onboarding")
    assert a._classify(-11.0) is EstimationClass.OVER
    assert a._classify(-10.0) is EstimationClass.WITHIN_TOLERANCE
    assert a._classify(10.0) is EstimationClass.WITHIN_TOLERANCE
    assert a._classify(11.0) is EstimationClass.UNDER
