"""Verdict derivation — score band + veto/cap gates (FR-8, ADR-0013, ADR-0014, ADR-0015).

The verdict is deterministic: a score band, then the most-restrictive of the band
and every triggered cap gate. INCOMPLETE (fewer than ``minimum_assessors`` available)
takes precedence over everything (ADR-0005).

Gate caps come from ``GateEngine`` (ADR-0014): assessors emit named gate signals on
``RiskFactor.gate``; the engine reads ``GatesConfig`` for the cap level; unnamed risk
factors fall back to severity (CRITICAL→NO_GO, MAJOR→CONDITIONAL).

ADR-0015 adds two additional caps applied after gate evaluation:
- Required dimensions: if a required dimension is unavailable, GO→CONDITIONAL.
- Confidence floor: if aggregate confidence < floor, GO→CONDITIONAL.

ADR-0016 items 4-5 add tier-aware threshold overrides: when ``tier_thresholds`` is
supplied, its go/no_go/confidence_floor/required_gate_dims replace the global values.
``excluded_gate_dims`` lists gate-only dimensions whose risk factors are suppressed for
the active tier (e.g. ACCESSIBILITY excluded for HOTFIX releases).
"""

from __future__ import annotations

from rrr.config.schema import GatesConfig, ThresholdsConfig, TierThresholds
from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName, Verdict
from rrr.orchestration.gate_engine import GateEngine

# Restrictiveness order for "most restrictive wins" (INCOMPLETE handled separately).
_RANK: dict[Verdict, int] = {Verdict.NO_GO: 0, Verdict.CONDITIONAL: 1, Verdict.GO: 2}


def most_restrictive(*verdicts: Verdict) -> Verdict:
    """Return the most restrictive verdict (NO_GO < CONDITIONAL < GO)."""
    return min(verdicts, key=lambda v: _RANK[v])


def score_band(score: float, go: float, no_go: float) -> Verdict:
    """Map a 0-1 score to its band (FR-8): GO >= go, NO_GO < no_go, else CONDITIONAL.

    Accepts explicit go/no_go thresholds rather than the full ThresholdsConfig so
    callers can pass either global or tier-specific thresholds without re-wrapping.
    """
    if score >= go:
        return Verdict.GO
    if score < no_go:
        return Verdict.NO_GO
    return Verdict.CONDITIONAL


def triggered_caps(
    results: list[DimensionResult],
    gates: GatesConfig,
    excluded_dims: list[DimensionName] | None = None,
) -> list[tuple[Verdict, str]]:
    """Return (cap, reason) for every gate-triggering risk factor across dimensions.

    ``excluded_dims`` is a list of gate-only dimension names whose risk factors are
    suppressed for the active tier (ADR-0016 items 4-5). Risk factors from those
    dimensions are filtered out before GateEngine evaluation so they do not cap the
    verdict even if they would ordinarily trigger a gate.
    """
    excluded = set(excluded_dims) if excluded_dims else set()
    all_risks = [
        risk
        for r in results
        if r.available
        for risk in r.risk_factors
        # Suppress risk factors from tier-excluded gate-only dimensions.
        if risk.dimension not in excluded
    ]
    return GateEngine.apply(all_risks, gates)


def derive_verdict(
    score: float,
    results: list[DimensionResult],
    thresholds: ThresholdsConfig,
    gates: GatesConfig,
    *,
    aggregate_confidence: float | None = None,
    tier_thresholds: TierThresholds | None = None,
) -> tuple[Verdict, list[str]]:
    """Return ``(verdict, gates_triggered)``.

    INCOMPLETE if fewer than ``minimum_assessors`` dimensions are available;
    otherwise the band capped by gate engine + ADR-0015 guards (most restrictive wins).

    When ``tier_thresholds`` is supplied (ADR-0016 items 4-5), its values override
    the global thresholds for go/no_go, confidence_floor, and required_gate_dims.
    The global ``minimum_assessors`` is always used (tiers do not relax that floor).
    """
    available = [r for r in results if r.available]
    if len(available) < thresholds.minimum_assessors:
        return Verdict.INCOMPLETE, []

    # Select effective threshold values — tier overrides global when active.
    eff_go = tier_thresholds.go if tier_thresholds is not None else thresholds.go
    eff_no_go = tier_thresholds.no_go if tier_thresholds is not None else thresholds.no_go
    eff_conf_floor = (
        tier_thresholds.confidence_floor
        if tier_thresholds is not None
        else thresholds.confidence_floor
    )
    eff_required_dims = (
        tier_thresholds.required_gate_dims
        if tier_thresholds is not None
        else thresholds.required_dimensions
    )
    excluded_dims = tier_thresholds.excluded_gate_dims if tier_thresholds is not None else None

    band = score_band(score, eff_go, eff_no_go)
    caps = triggered_caps(results, gates, excluded_dims=excluded_dims)
    verdict = most_restrictive(band, *(cap for cap, _ in caps)) if caps else band
    reasons = [reason for _, reason in caps]

    # ADR-0015: required dimensions must be present for a GO verdict.
    if verdict is Verdict.GO and eff_required_dims:
        available_dims = {r.dimension for r in available}
        missing = [dim for dim in eff_required_dims if dim not in available_dims]
        for dim in missing:
            reasons.append(
                f"Required dimension '{dim.value}' unavailable"
                " — GO capped to CONDITIONAL (ADR-0015)"
            )
        if missing:
            verdict = Verdict.CONDITIONAL

    # ADR-0015: confidence floor caps GO → CONDITIONAL.
    if (
        verdict is Verdict.GO
        and aggregate_confidence is not None
        and aggregate_confidence < eff_conf_floor
    ):
        reasons.append(
            f"Aggregate confidence {aggregate_confidence:.2f} below floor "
            f"{eff_conf_floor:.2f} — GO capped to CONDITIONAL (ADR-0015)"
        )
        verdict = Verdict.CONDITIONAL

    return verdict, reasons
