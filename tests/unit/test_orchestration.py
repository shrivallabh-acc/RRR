"""Orchestration tests: scoring + verdict units, and full golden integration runs."""

from __future__ import annotations

import time
from pathlib import Path

from rrr.assessors import (
    DependencyAssessor,
    EnvironmentAssessor,
    EstimationAssessor,
    OperabilityAssessor,
    ScopeAssessor,
)
from rrr.assessors import (
    TestReadinessAssessor as ReadinessAssessor,
)  # aliased: avoid pytest collection
from rrr.assessors.base import BaseAssessor
from rrr.config import ConfigLoader
from rrr.config.schema import RRRConfig
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor
from rrr.orchestration import (
    Orchestrator,
    derive_verdict,
    most_restrictive,
    score_band,
    weighted_score,
)
from rrr.providers import RuleBasedProvider
from rrr.tools import (
    DependencySourceReader,
    EnvironmentSourceReader,
    OperabilitySourceReader,
    RKTBrainReader,
    ToolRunner,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
VS = "Retirement-Services"
CFG = ConfigLoader.load()
WEIGHTS = {
    DimensionName.SCOPE: 0.25,
    DimensionName.ESTIMATION: 0.10,
    DimensionName.ENVIRONMENT: 0.20,
    DimensionName.TEST_READINESS: 0.30,
    DimensionName.DEPENDENCY: 0.15,
}


def _dim(
    name: DimensionName,
    score: float,
    *,
    available: bool = True,
    risks: tuple[RiskFactor, ...] = (),
) -> DimensionResult:
    return DimensionResult(
        dimension=name, available=available, score=score, confidence=1.0, risk_factors=list(risks)
    )


# --- scoring (FR-7) ---------------------------------------------------------------------------


def test_weighted_score_all_available() -> None:
    results = [_dim(d, 1.0) for d in DimensionName]
    score, eff = weighted_score(results, WEIGHTS)
    assert abs(score - 1.0) < 1e-9
    assert abs(sum(eff.values()) - 1.0) < 1e-9


def test_weight_redistribution_for_unavailable() -> None:
    results = [
        _dim(DimensionName.SCOPE, 1.0),
        _dim(DimensionName.ESTIMATION, 0.0),
    ]
    score, eff = weighted_score(results, WEIGHTS)
    # only scope (.25) + estimation (.10) available -> renormalized to .714/.286
    assert abs(eff[DimensionName.SCOPE] - 0.25 / 0.35) < 1e-9
    assert abs(score - (0.25 / 0.35)) < 1e-9  # estimation contributes 0


def test_no_available_dimensions_scores_zero() -> None:
    results = [_dim(DimensionName.SCOPE, 0.9, available=False)]
    assert weighted_score(results, WEIGHTS) == (0.0, {})


# --- verdict + gates (FR-8, ADR-0013) ---------------------------------------------------------


def test_score_bands() -> None:
    go, no_go = CFG.thresholds.go, CFG.thresholds.no_go
    assert score_band(0.80, go, no_go) is Verdict.GO
    assert score_band(0.79, go, no_go) is Verdict.CONDITIONAL
    assert score_band(0.40, go, no_go) is Verdict.CONDITIONAL
    assert score_band(0.39, go, no_go) is Verdict.NO_GO


def test_most_restrictive() -> None:
    assert most_restrictive(Verdict.GO, Verdict.NO_GO) is Verdict.NO_GO
    assert most_restrictive(Verdict.GO, Verdict.CONDITIONAL) is Verdict.CONDITIONAL


def test_incomplete_when_below_minimum_assessors() -> None:
    results = [_dim(DimensionName.SCOPE, 1.0), _dim(DimensionName.ESTIMATION, 1.0)]  # only 2 < 4
    verdict, gates = derive_verdict(1.0, results, CFG.thresholds, CFG.gates)
    assert verdict is Verdict.INCOMPLETE and gates == []


def test_critical_risk_caps_to_no_go() -> None:
    risk = RiskFactor(description="E2E below floor", severity=RiskSeverity.CRITICAL)
    results = [_dim(d, 1.0) for d in DimensionName]
    results[3] = _dim(DimensionName.TEST_READINESS, 0.9, risks=(risk,))
    verdict, gates = derive_verdict(0.95, results, CFG.thresholds, CFG.gates)  # GO band
    assert verdict is Verdict.NO_GO and "E2E below floor" in gates


def test_major_risk_caps_to_conditional() -> None:
    risk = RiskFactor(description="scope grew 30%", severity=RiskSeverity.MAJOR)
    results = [_dim(d, 1.0) for d in DimensionName]
    results[0] = _dim(DimensionName.SCOPE, 0.94, risks=(risk,))
    verdict, _ = derive_verdict(0.93, results, CFG.thresholds, CFG.gates)  # GO band
    assert verdict is Verdict.CONDITIONAL


def test_gates_disabled_skips_caps() -> None:
    disabled = CFG.gates.model_copy(update={"enabled": False})
    risk = RiskFactor(description="critical thing", severity=RiskSeverity.CRITICAL)
    results = [_dim(d, 1.0) for d in DimensionName]
    results[3] = _dim(DimensionName.TEST_READINESS, 0.9, risks=(risk,))
    verdict, gates = derive_verdict(0.95, results, CFG.thresholds, disabled)
    assert verdict is Verdict.GO and gates == []


# --- full integration over the golden fixtures (ADR-0013 expectations) -----------------------


def _wire(sample: str, ir_name: str) -> list[BaseAssessor]:
    inputs = GOLDEN / sample / "inputs"
    provider = RuleBasedProvider()
    runner = ToolRunner()
    brain = RKTBrainReader(inputs / "brain")
    common = {"value_stream": VS, "ir_name": ir_name}
    return [
        ScopeAssessor(
            runner, provider, brain, scope_creep_threshold=CFG.gates.scope_creep_threshold, **common
        ),
        EstimationAssessor(runner, provider, brain, **common),
        ReadinessAssessor(
            runner, provider, brain, e2e_critical_floor=CFG.gates.e2e_critical_floor, **common
        ),
        EnvironmentAssessor(
            runner, provider, EnvironmentSourceReader(path=inputs / "environment.json")
        ),
        DependencyAssessor(
            runner, provider, DependencySourceReader(path=inputs / "dependency.json")
        ),
        OperabilityAssessor(
            runner, provider, OperabilitySourceReader(path=inputs / "operability.json")
        ),
    ]


def _run(sample: str, ir_name: str, config: RRRConfig = CFG) -> object:
    orch = Orchestrator(config, RuleBasedProvider())
    return orch.run(_wire(sample, ir_name), release=ir_name, value_stream=VS)


def test_g1_clean_release_is_go_96() -> None:
    out = _run("g1_clean_release", "Launch 36 - Unified Onboarding")
    assert out.verdict is Verdict.GO
    assert out.score == 97  # observability opt-in not wired; weight redistributes across 6 dims
    assert len(out.dimensions) == 6 and all(d.available for d in out.dimensions)
    assert out.audit_trail.gates_triggered == []
    assert abs(sum(out.audit_trail.effective_weights.values()) - 1.0) < 1e-9


def test_g2_failing_tests_is_no_go_via_e2e_gate() -> None:
    out = _run("g2_failing_tests", "Launch 37 - Payments Hub")
    assert out.verdict is Verdict.NO_GO
    assert any("E2E" in g for g in out.audit_trail.gates_triggered)


def test_g3_borderline_is_conditional_via_dependency_gate() -> None:
    out = _run("g3_borderline", "Launch 38 - Advice Workbench")
    assert out.verdict is Verdict.CONDITIONAL
    assert out.score == 74
    assert any("notification hub" in g.lower() for g in out.audit_trail.gates_triggered)


def test_g4_missing_data_is_incomplete() -> None:
    out = _run("g4_missing_data", "Launch 39 - Missing Data")
    assert out.verdict is Verdict.INCOMPLETE
    available = [d for d in out.dimensions if d.available]
    assert len(available) == 3  # environment + dependency + operability
    assert all(d.dimension in ("environment", "dependency", "operability") for d in available)
    assert abs(sum(out.audit_trail.effective_weights.values()) - 1.0) < 1e-9


def test_g5_scope_creep_is_conditional() -> None:
    out = _run("g5_scope_creep", "Launch 40 - Onboarding Plus")
    assert out.verdict is Verdict.CONDITIONAL
    assert any("scope grew" in g.lower() for g in out.audit_trail.gates_triggered)


def test_output_carries_rationale_and_remediation() -> None:
    out = _run("g5_scope_creep", "Launch 40 - Onboarding Plus")
    assert out.rationale  # synthesized by the provider
    assert out.remediation  # derived from the risk factors
    assert out.schema_version == "1.0.0"


def test_aggregate_confidence_is_set_on_output() -> None:
    out = _run("g1_clean_release", "Launch 36 - Unified Onboarding")
    assert out.aggregate_confidence is not None
    assert 0.0 <= out.aggregate_confidence <= 1.0


# --- ADR-0015: required dimensions + confidence floor ------------------------------------


def test_required_dimension_unavailable_caps_go_to_conditional() -> None:
    # Build a config where test_readiness and environment are required, but only pass
    # results without test_readiness — score is GO band but verdict must be CONDITIONAL.
    thresholds_no_required = CFG.thresholds.model_copy(update={"required_dimensions": []})
    thresholds_with_required = CFG.thresholds  # includes [test_readiness, environment] by default

    results = [
        _dim(DimensionName.SCOPE, 1.0),
        _dim(DimensionName.ESTIMATION, 1.0),
        _dim(DimensionName.ENVIRONMENT, 1.0),
        _dim(DimensionName.DEPENDENCY, 1.0),
        # TEST_READINESS is unavailable
        _dim(DimensionName.TEST_READINESS, 0.0, available=False),
    ]
    score = 1.0  # would be GO if no required-dim check

    verdict_base, _ = derive_verdict(score, results, thresholds_no_required, CFG.gates)
    assert verdict_base is Verdict.GO  # confirms score band alone would be GO

    verdict_guarded, reasons = derive_verdict(score, results, thresholds_with_required, CFG.gates)
    assert verdict_guarded is Verdict.CONDITIONAL
    assert any("test_readiness" in r for r in reasons)


def test_confidence_floor_caps_go_to_conditional() -> None:
    # All five dims available, score in GO band, but confidence is low.
    results = [_dim(d, 1.0) for d in DimensionName]
    # Confidence = 1.0 for all, so normally no cap. Override via kwarg.
    verdict, reasons = derive_verdict(
        0.95, results, CFG.thresholds, CFG.gates, aggregate_confidence=0.50
    )
    assert verdict is Verdict.CONDITIONAL
    assert any("confidence" in r.lower() for r in reasons)


def test_confidence_above_floor_does_not_cap() -> None:
    results = [_dim(d, 1.0) for d in DimensionName]
    verdict, _ = derive_verdict(0.95, results, CFG.thresholds, CFG.gates, aggregate_confidence=0.90)
    assert verdict is Verdict.GO


def test_confidence_floor_does_not_affect_no_go() -> None:
    # Low confidence should not change a NO_GO result.
    risk = RiskFactor(description="critical issue", severity=RiskSeverity.CRITICAL)
    results = [_dim(d, 0.5) for d in DimensionName]
    results[0] = _dim(DimensionName.SCOPE, 0.5, risks=(risk,))
    verdict, _ = derive_verdict(0.50, results, CFG.thresholds, CFG.gates, aggregate_confidence=0.30)
    assert verdict is Verdict.NO_GO  # gate cap wins; confidence floor doesn't downgrade further


# --- W6: per-assessor timeout (NFR-1) -----------------------------------------------------------


class _HangingAssessor(BaseAssessor):
    """Stub assessor that blocks indefinitely — used to test the fan-out timeout."""

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.ESTIMATION

    def _assess(self) -> object:
        time.sleep(9999)  # never returns within any realistic timeout
        raise AssertionError("unreachable")  # pragma: no cover


def _fast_config(timeout_secs: int = 1) -> RRRConfig:
    """Return a config with a very short assessor_default timeout for test speed."""
    timeouts = CFG.timeouts.model_copy(update={"assessor_default": timeout_secs})
    return CFG.model_copy(update={"timeouts": timeouts})


def test_timed_out_assessor_is_marked_unavailable() -> None:
    # A hanging assessor must produce an unavailable DimensionResult, not block the run.
    hanging = _HangingAssessor(ToolRunner(), RuleBasedProvider())
    orch = Orchestrator(_fast_config(timeout_secs=1), RuleBasedProvider())
    results = orch._fan_out([hanging])
    assert len(results) == 1
    assert results[0].available is False
    assert "timed out" in (results[0].narrative or "").lower()


def test_timeout_does_not_affect_completing_assessors() -> None:
    # When one assessor hangs, the others still produce valid results.
    inputs = GOLDEN / "g1_clean_release" / "inputs"
    provider = RuleBasedProvider()
    runner = ToolRunner()
    brain = RKTBrainReader(inputs / "brain")
    fast_scope = ScopeAssessor(
        runner,
        provider,
        brain,
        value_stream=VS,
        ir_name="Launch 36 - Unified Onboarding",
        scope_creep_threshold=CFG.gates.scope_creep_threshold,
    )
    hanging = _HangingAssessor(runner, provider)
    orch = Orchestrator(_fast_config(timeout_secs=1), provider)
    results = orch._fan_out([fast_scope, hanging])
    assert len(results) == 2
    scope_r = next(r for r in results if r.dimension == DimensionName.SCOPE)
    hang_r = next(r for r in results if r.dimension == DimensionName.ESTIMATION)
    assert scope_r.available is True
    assert hang_r.available is False


def test_fan_out_completes_within_timeout_window() -> None:
    # All 6 real assessors finish well within a generous timeout — result count stays 6.
    out = _run("g1_clean_release", "Launch 36 - Unified Onboarding", _fast_config(timeout_secs=30))
    assert len(out.dimensions) == 6
    assert all(d.available for d in out.dimensions)
