"""Tests for ReadinessAssessor (FR-4, ADR-0012) — real fixtures + E2E-absent fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Aliased so pytest does not try to collect the production class as a test class.
from rrr.assessors import TestReadinessAssessor as ReadinessAssessor
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.providers import RuleBasedProvider
from rrr.tools import RKTBrainReader, ToolRunner
from rrr.tools.brain_reader import BrainReadResult

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
G1_BRAIN = GOLDEN / "g1_clean_release" / "inputs" / "brain"
G2_BRAIN = GOLDEN / "g2_failing_tests" / "inputs" / "brain"
VS = "Retirement-Services"


def _assessor(brain_dir: Path, ir_name: str) -> ReadinessAssessor:
    return ReadinessAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        RKTBrainReader(brain_dir),
        value_stream=VS,
        ir_name=ir_name,
    )


def test_g1_clean_release_ready() -> None:
    result = _assessor(G1_BRAIN, "Launch 36 - Unified Onboarding").assess()
    assert result.dimension is DimensionName.TEST_READINESS and result.available is True
    assert abs(result.score - 0.953) < 0.03  # matches g1 ideal.json
    assert result.classification == "ready"
    assert result.confidence == 1.0
    assert result.risk_factors == []


def test_g2_failing_tests_low_score_with_risks() -> None:
    result = _assessor(G2_BRAIN, "Launch 37 - Payments Hub").assess()
    assert abs(result.score - 0.315) < 0.03  # quality .6, defect 0, e2e .25
    assert result.classification == "not_ready"
    # 1 open critical defect + 1 sub-quality repo surface as risks
    sevs = {rf.severity for rf in result.risk_factors}
    assert RiskSeverity.MAJOR in sevs  # critical defect
    assert RiskSeverity.MINOR in sevs  # sq_below_1 repo
    assert any("critical" in rf.description.lower() for rf in result.risk_factors)


def test_defect_trend_direction() -> None:
    f = ReadinessAssessor._defect_trend_score
    assert f([14, 13, 12, 11, 10]) == 1.0  # declining -> improving
    assert f([6, 8, 10, 12, 14]) == 0.0  # rising -> worsening
    assert f([9, 9, 9, 9, 9]) == 0.5  # flat
    assert f([5]) == 0.5  # insufficient


def test_e2e_absent_renormalizes_and_caps_confidence() -> None:
    """A release with no E2E data is scored on quality+defect and confidence is capped."""

    class _FakeReader:
        name = "rkt_brain_reader"

        def __init__(self) -> None:
            base = RKTBrainReader(G1_BRAIN).read(
                value_stream=VS, ir_name="Launch 36 - Unified Onboarding"
            )
            release_no_e2e = base.release.model_copy(update={"e2e_latest": None})
            self._result = base.model_copy(update={"release": release_no_e2e})

        def invoke(self, **params: Any) -> BrainReadResult:
            return self._result

    assessor = ReadinessAssessor(
        ToolRunner(),
        RuleBasedProvider(),
        _FakeReader(),
        value_stream=VS,  # type: ignore[arg-type]
    )
    result = assessor.assess()
    # renormalized: 0.571*quality(0.9) + 0.429*defect(1.0) = 0.9514…
    assert abs(result.score - 0.9514) < 0.01
    assert result.confidence == 0.5  # capped despite the tool succeeding
    assert "E2E results absent" in result.narrative  # surfaced via the composed narrative
