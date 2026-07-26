"""Property-based tests for scoring & verdict invariants and determinism (FR-29, NFR-6).

These guard the deterministic core: whatever random mix of dimension results comes
out of the assessors, the score stays in range, weights redistribute to sum 1.0,
the verdict is reproducible, and the ADR-0013 gate/INCOMPLETE rules always hold.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rrr.config import ConfigLoader
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor
from rrr.orchestration import derive_verdict, most_restrictive, score_band, weighted_score

pytestmark = pytest.mark.property

CFG = ConfigLoader.load()
WEIGHTS = {
    DimensionName.SCOPE: 0.25,
    DimensionName.ESTIMATION: 0.10,
    DimensionName.ENVIRONMENT: 0.20,
    DimensionName.TEST_READINESS: 0.30,
    DimensionName.DEPENDENCY: 0.15,
}
_RANK = {Verdict.NO_GO: 0, Verdict.CONDITIONAL: 1, Verdict.GO: 2}

_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_severities = st.sampled_from(list(RiskSeverity))


@st.composite
def assessment_results(draw: st.DrawFn) -> list[DimensionResult]:
    """One result per dimension with random availability, score, and risk factors."""
    results: list[DimensionResult] = []
    for dim in DimensionName:
        n_risks = draw(st.integers(min_value=0, max_value=2))
        risks = [
            RiskFactor(description=f"{dim.value}-r{i}", severity=draw(_severities))
            for i in range(n_risks)
        ]
        results.append(
            DimensionResult(
                dimension=dim,
                available=draw(st.booleans()),
                score=draw(_scores),
                confidence=1.0,
                risk_factors=risks,
            )
        )
    return results


@given(assessment_results())
def test_score_always_in_range_and_weights_normalized(results: list[DimensionResult]) -> None:
    score, effective = weighted_score(results, WEIGHTS)
    assert 0.0 <= score <= 1.0
    if any(r.available for r in results):
        assert abs(sum(effective.values()) - 1.0) < 1e-9
    else:
        assert score == 0.0 and effective == {}


@given(assessment_results())
def test_verdict_is_deterministic(results: list[DimensionResult]) -> None:
    score, _ = weighted_score(results, WEIGHTS)
    first = derive_verdict(score, results, CFG.thresholds, CFG.gates)
    second = derive_verdict(score, results, CFG.thresholds, CFG.gates)
    assert first == second


@given(assessment_results())
def test_incomplete_iff_below_minimum_assessors(results: list[DimensionResult]) -> None:
    score, _ = weighted_score(results, WEIGHTS)
    verdict, _ = derive_verdict(score, results, CFG.thresholds, CFG.gates)
    available = sum(1 for r in results if r.available)
    assert (verdict is Verdict.INCOMPLETE) == (available < CFG.thresholds.minimum_assessors)


@given(assessment_results())
def test_critical_risk_forces_no_go_when_complete(results: list[DimensionResult]) -> None:
    score, _ = weighted_score(results, WEIGHTS)
    verdict, _ = derive_verdict(score, results, CFG.thresholds, CFG.gates)
    available = [r for r in results if r.available]
    has_critical = any(
        rf.severity is RiskSeverity.CRITICAL for r in available for rf in r.risk_factors
    )
    if len(available) >= CFG.thresholds.minimum_assessors and has_critical:
        assert verdict is Verdict.NO_GO


@given(_scores, _scores)
def test_score_band_is_monotonic(a: float, b: float) -> None:
    lo, hi = sorted((a, b))
    assert (
        _RANK[score_band(lo, CFG.thresholds.go, CFG.thresholds.no_go)]
        <= _RANK[score_band(hi, CFG.thresholds.go, CFG.thresholds.no_go)]
    )


@given(st.lists(st.sampled_from(list(Verdict.__members__.values())), min_size=1, max_size=4))
def test_most_restrictive_picks_lowest_rank(verdicts: list[Verdict]) -> None:
    capped = [v for v in verdicts if v in _RANK]  # exclude INCOMPLETE (not part of capping)
    if not capped:
        return
    result = most_restrictive(*capped)
    assert _RANK[result] == min(_RANK[v] for v in capped)
