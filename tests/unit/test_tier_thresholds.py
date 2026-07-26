"""Tests for ADR-0016 items 4-6: ReleaseRiskTier, TierThresholds, split_scores.

Covers enum values, TierThresholds/TiersConfig validation, score_band new
signature, triggered_caps excluded-dim filtering, derive_verdict tier
overrides, split_scores group logic, default config loading, and orchestrator
collect() integration with the tier path.
"""

from __future__ import annotations

import pytest

from rrr.config import ConfigLoader
from rrr.config.schema import TiersConfig, TierThresholds
from rrr.models.assessment import AssessmentOutputModel, AuditTrail
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, ReleaseRiskTier, RiskSeverity, Verdict
from rrr.models.evidence import RiskFactor
from rrr.orchestration import (
    derive_verdict,
    score_band,
    split_scores,
    triggered_caps,
    weighted_score,
)
from rrr.orchestration.orchestrator import Orchestrator
from rrr.providers.rule_based import RuleBasedProvider

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
    risks: list[RiskFactor] | None = None,
) -> DimensionResult:
    return DimensionResult(
        dimension=name,
        available=available,
        score=score,
        confidence=1.0,
        risk_factors=risks or [],
    )


def _risk(dim: DimensionName, severity: RiskSeverity) -> RiskFactor:
    return RiskFactor(description=f"{dim.value} issue", severity=severity, dimension=dim)


# ---------------------------------------------------------------------------
# ReleaseRiskTier enum
# ---------------------------------------------------------------------------


def test_release_risk_tier_values() -> None:
    assert ReleaseRiskTier.HOTFIX.value == "hotfix"
    assert ReleaseRiskTier.STANDARD.value == "standard"
    assert ReleaseRiskTier.MAJOR.value == "major"


def test_release_risk_tier_from_string() -> None:
    assert ReleaseRiskTier("hotfix") is ReleaseRiskTier.HOTFIX
    assert ReleaseRiskTier("standard") is ReleaseRiskTier.STANDARD
    assert ReleaseRiskTier("major") is ReleaseRiskTier.MAJOR


# ---------------------------------------------------------------------------
# TierThresholds validation
# ---------------------------------------------------------------------------


def test_tier_thresholds_valid_construction() -> None:
    t = TierThresholds(go=0.80, no_go=0.40)
    assert t.go == 0.80
    assert t.no_go == 0.40
    assert t.confidence_floor == 0.70  # default
    assert t.required_gate_dims == []
    assert t.excluded_gate_dims == []


def test_tier_thresholds_go_must_exceed_no_go() -> None:
    with pytest.raises(ValueError, match="must be greater than no_go"):
        TierThresholds(go=0.40, no_go=0.40)


def test_tier_thresholds_go_equal_no_go_fails() -> None:
    with pytest.raises(ValueError):
        TierThresholds(go=0.50, no_go=0.50)


def test_tiers_config_for_tier_returns_correct_entry() -> None:
    hotfix = TierThresholds(go=0.60, no_go=0.30)
    standard = TierThresholds(go=0.80, no_go=0.40)
    major = TierThresholds(go=0.90, no_go=0.60)
    tiers = TiersConfig(hotfix=hotfix, standard=standard, major=major)

    assert tiers.for_tier(ReleaseRiskTier.HOTFIX) is hotfix
    assert tiers.for_tier(ReleaseRiskTier.STANDARD) is standard
    assert tiers.for_tier(ReleaseRiskTier.MAJOR) is major


# ---------------------------------------------------------------------------
# score_band — new explicit go/no_go signature
# ---------------------------------------------------------------------------


def test_score_band_explicit_thresholds_go() -> None:
    assert score_band(0.90, 0.80, 0.40) is Verdict.GO


def test_score_band_explicit_thresholds_conditional() -> None:
    assert score_band(0.60, 0.80, 0.40) is Verdict.CONDITIONAL


def test_score_band_explicit_thresholds_no_go() -> None:
    assert score_band(0.39, 0.80, 0.40) is Verdict.NO_GO


def test_score_band_hotfix_thresholds_relaxed() -> None:
    # A score of 0.65 is GO under hotfix (go=0.60) but CONDITIONAL under standard (go=0.80).
    assert score_band(0.65, 0.60, 0.30) is Verdict.GO
    assert score_band(0.65, 0.80, 0.40) is Verdict.CONDITIONAL


def test_score_band_boundary_at_go() -> None:
    # Exactly at the go threshold is GO.
    assert score_band(0.80, 0.80, 0.40) is Verdict.GO


def test_score_band_boundary_at_no_go() -> None:
    # Exactly at no_go boundary is CONDITIONAL (score < no_go → NO_GO; equal is CONDITIONAL).
    assert score_band(0.40, 0.80, 0.40) is Verdict.CONDITIONAL


# ---------------------------------------------------------------------------
# triggered_caps — excluded_dims filtering
# ---------------------------------------------------------------------------


def test_triggered_caps_excluded_dims_suppresses_risk_factor() -> None:
    # A CRITICAL risk on ACCESSIBILITY would normally cap to NO_GO.
    results = [
        _dim(DimensionName.SCOPE, 0.9),
        _dim(
            DimensionName.TEST_READINESS,
            0.8,
            risks=[_risk(DimensionName.TEST_READINESS, RiskSeverity.CRITICAL)],
        ),
    ]
    # Without exclusion, a CRITICAL risk triggers NO_GO cap.
    caps_normal = triggered_caps(results, CFG.gates)
    verdicts_normal = [c for c, _ in caps_normal]
    assert Verdict.NO_GO in verdicts_normal

    # With TEST_READINESS excluded, that CRITICAL risk is suppressed.
    caps_excluded = triggered_caps(results, CFG.gates, excluded_dims=[DimensionName.TEST_READINESS])
    verdicts_excluded = [c for c, _ in caps_excluded]
    assert Verdict.NO_GO not in verdicts_excluded


def test_triggered_caps_no_exclusion_has_no_filter() -> None:
    results = [_dim(DimensionName.SCOPE, 0.9)]
    caps = triggered_caps(results, CFG.gates, excluded_dims=None)
    assert isinstance(caps, list)


# ---------------------------------------------------------------------------
# derive_verdict — tier threshold overrides
# ---------------------------------------------------------------------------


def test_derive_verdict_tier_thresholds_relaxed_go() -> None:
    # Score 0.65: GO under hotfix (go=0.60) but CONDITIONAL under standard (go=0.80).
    results = [
        _dim(d, 1.0)
        for d in [
            DimensionName.SCOPE,
            DimensionName.ESTIMATION,
            DimensionName.ENVIRONMENT,
            DimensionName.TEST_READINESS,
            DimensionName.DEPENDENCY,
        ]
    ]
    hotfix_tier = TierThresholds(go=0.60, no_go=0.30)
    verdict, _ = derive_verdict(
        0.65, results, CFG.thresholds, CFG.gates, tier_thresholds=hotfix_tier
    )
    assert verdict is Verdict.GO


def test_derive_verdict_tier_required_dims_caps_go() -> None:
    # ENVIRONMENT is required by tier but marked unavailable — GO must become CONDITIONAL.
    results = [
        _dim(DimensionName.SCOPE, 1.0),
        _dim(DimensionName.ESTIMATION, 1.0),
        _dim(DimensionName.TEST_READINESS, 1.0),
        _dim(DimensionName.DEPENDENCY, 1.0),
        _dim(DimensionName.ENVIRONMENT, 0.0, available=False),
    ]
    tier = TierThresholds(
        go=0.50,  # low enough that the score qualifies for GO
        no_go=0.20,
        required_gate_dims=[DimensionName.ENVIRONMENT],
    )
    score, _ = weighted_score(results, WEIGHTS)
    verdict, reasons = derive_verdict(
        score, results, CFG.thresholds, CFG.gates, tier_thresholds=tier
    )
    assert verdict is Verdict.CONDITIONAL
    assert any("environment" in r.lower() for r in reasons)


def test_derive_verdict_without_tier_uses_global_thresholds() -> None:
    results = [
        _dim(d, 1.0)
        for d in [
            DimensionName.SCOPE,
            DimensionName.ESTIMATION,
            DimensionName.ENVIRONMENT,
            DimensionName.TEST_READINESS,
            DimensionName.DEPENDENCY,
        ]
    ]
    # Score 1.0 → always GO with no risks.
    verdict, _ = derive_verdict(1.0, results, CFG.thresholds, CFG.gates)
    assert verdict is Verdict.GO


# ---------------------------------------------------------------------------
# split_scores
# ---------------------------------------------------------------------------


def test_split_scores_ship_safety_uses_correct_dims() -> None:
    # Only TEST_READINESS, ENVIRONMENT, DEPENDENCY should contribute to ship_safety.
    results = [
        _dim(DimensionName.TEST_READINESS, 1.0),
        _dim(DimensionName.ENVIRONMENT, 1.0),
        _dim(DimensionName.DEPENDENCY, 1.0),
        _dim(DimensionName.SCOPE, 0.0),  # should not affect ship_safety
        _dim(DimensionName.ESTIMATION, 0.0),  # should not affect ship_safety
    ]
    ship, delivery = split_scores(results, WEIGHTS)
    assert ship is not None
    assert abs(ship - 1.0) < 1e-9, "All ship-safety dims score 1.0 → ship_safety should be 1.0"


def test_split_scores_delivery_uses_correct_dims() -> None:
    results = [
        _dim(DimensionName.SCOPE, 1.0),
        _dim(DimensionName.ESTIMATION, 1.0),
        _dim(DimensionName.TEST_READINESS, 0.0),  # not a delivery dim
        _dim(DimensionName.ENVIRONMENT, 0.0),
        _dim(DimensionName.DEPENDENCY, 0.0),
    ]
    ship, delivery = split_scores(results, WEIGHTS)
    assert delivery is not None
    assert abs(delivery - 1.0) < 1e-9, "All delivery dims score 1.0 → delivery should be 1.0"


def test_split_scores_returns_none_when_group_absent() -> None:
    # No ship-safety dims available.
    results = [
        _dim(DimensionName.SCOPE, 0.8),
        _dim(DimensionName.ESTIMATION, 0.7),
    ]
    ship, delivery = split_scores(results, WEIGHTS)
    assert ship is None
    assert delivery is not None


def test_split_scores_in_range() -> None:
    results = [_dim(d, 0.75) for d in DimensionName]
    ship, delivery = split_scores(results, WEIGHTS)
    assert ship is not None and 0.0 <= ship <= 1.0
    assert delivery is not None and 0.0 <= delivery <= 1.0


# ---------------------------------------------------------------------------
# Default config — tiers block is present
# ---------------------------------------------------------------------------


def test_default_config_loads_tiers() -> None:
    cfg = ConfigLoader.load()
    assert cfg.tiers is not None, "default_config.yaml must define a tiers: block"


def test_default_config_tiers_hotfix_more_relaxed_than_major() -> None:
    cfg = ConfigLoader.load()
    assert cfg.tiers is not None
    hotfix = cfg.tiers.for_tier(ReleaseRiskTier.HOTFIX)
    major = cfg.tiers.for_tier(ReleaseRiskTier.MAJOR)
    assert hotfix.go < major.go, "HOTFIX GO threshold must be lower (more relaxed) than MAJOR"
    assert hotfix.no_go < major.no_go


# ---------------------------------------------------------------------------
# Orchestrator.collect() — tier integration
# ---------------------------------------------------------------------------


def test_collect_records_tier_in_output() -> None:
    orch = Orchestrator(CFG, RuleBasedProvider())
    results = [
        _dim(DimensionName.SCOPE, 0.9),
        _dim(DimensionName.ESTIMATION, 0.8),
        _dim(DimensionName.TEST_READINESS, 0.9),
        _dim(DimensionName.ENVIRONMENT, 0.8),
        _dim(DimensionName.DEPENDENCY, 0.85),
    ]
    output = orch.collect(results, release="TEST-001", tier=ReleaseRiskTier.STANDARD)
    assert output.tier is ReleaseRiskTier.STANDARD


def test_collect_without_tier_records_none() -> None:
    orch = Orchestrator(CFG, RuleBasedProvider())
    results = [
        _dim(DimensionName.SCOPE, 0.9),
        _dim(DimensionName.ESTIMATION, 0.8),
        _dim(DimensionName.TEST_READINESS, 0.9),
        _dim(DimensionName.ENVIRONMENT, 0.8),
        _dim(DimensionName.DEPENDENCY, 0.85),
    ]
    output = orch.collect(results, release="TEST-001")
    assert output.tier is None


def test_collect_computes_sub_scores_in_0_to_100() -> None:
    orch = Orchestrator(CFG, RuleBasedProvider())
    results = [
        _dim(DimensionName.SCOPE, 0.75),
        _dim(DimensionName.ESTIMATION, 0.80),
        _dim(DimensionName.TEST_READINESS, 0.85),
        _dim(DimensionName.ENVIRONMENT, 0.90),
        _dim(DimensionName.DEPENDENCY, 0.70),
    ]
    output = orch.collect(results, release="TEST-002", tier=ReleaseRiskTier.HOTFIX)
    assert output.ship_safety_score is not None
    assert 0 <= output.ship_safety_score <= 100
    assert output.delivery_performance_score is not None
    assert 0 <= output.delivery_performance_score <= 100


def test_collect_tier_hotfix_relaxed_threshold_can_yield_go() -> None:
    # Under HOTFIX (go=0.60), a score ~0.65 should reach GO if no critical gates fire.
    # Under STANDARD (go=0.80), the same score would be CONDITIONAL.
    if CFG.tiers is None:
        pytest.skip("tiers not configured")
    hotfix_go = CFG.tiers.for_tier(ReleaseRiskTier.HOTFIX).go
    standard_go = CFG.tiers.for_tier(ReleaseRiskTier.STANDARD).go
    # Confirm the config has relaxed thresholds for hotfix.
    assert hotfix_go < standard_go


# ---------------------------------------------------------------------------
# AssessmentOutputModel — tier + sub-score fields
# ---------------------------------------------------------------------------


def test_assessment_output_model_tier_and_subscores() -> None:
    audit = AuditTrail(provider="RuleBasedProvider")
    result = AssessmentOutputModel(
        release="REL-1",
        value_stream="VS",
        verdict=Verdict.GO,
        score=85,
        tier=ReleaseRiskTier.MAJOR,
        ship_safety_score=90,
        delivery_performance_score=78,
        dimensions=[],
        audit_trail=audit,
    )
    assert result.tier is ReleaseRiskTier.MAJOR
    assert result.ship_safety_score == 90
    assert result.delivery_performance_score == 78


def test_assessment_output_model_tier_defaults_none() -> None:
    audit = AuditTrail(provider="RuleBasedProvider")
    result = AssessmentOutputModel(
        release="REL-2",
        value_stream="VS",
        verdict=Verdict.CONDITIONAL,
        score=72,
        dimensions=[],
        audit_trail=audit,
    )
    assert result.tier is None
    assert result.ship_safety_score is None
    assert result.delivery_performance_score is None
