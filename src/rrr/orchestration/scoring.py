"""Weighted scoring with redistribution for unavailable dimensions (FR-7).

Only *available* dimensions contribute. The configured weight of any unavailable
dimension is redistributed across the available ones in proportion to their
configured weights, so the remaining dimensions still sum to 1.0 and the score
stays comparable. Returns the 0-1 score and the effective weights actually used
(recorded in the audit trail).

``split_scores()`` computes ship-safety and delivery-performance sub-scores from
the same weight map (ADR-0016 item 6). Ship-safety = TEST_READINESS + ENVIRONMENT +
DEPENDENCY + OPERABILITY + OBSERVABILITY; delivery-performance = SCOPE + ESTIMATION.
Each group is scored independently with the same redistribution logic.
"""

from __future__ import annotations

from rrr.models.dimension import DimensionResult
from rrr.models.enums import DimensionName

# Ship-safety dims gate safe deployment (ADR-0016 item 6, updated by item-7 split).
# OPERABILITY and OBSERVABILITY added: deployment pipeline health and monitoring
# coverage are direct ship-safety signals, not delivery-performance signals.
_SHIP_SAFETY_DIMS: frozenset[DimensionName] = frozenset(
    [
        DimensionName.TEST_READINESS,
        DimensionName.ENVIRONMENT,
        DimensionName.DEPENDENCY,
        DimensionName.OPERABILITY,
        DimensionName.OBSERVABILITY,
    ]
)
# Delivery-performance dims reflect programme estimation / scope delivery quality.
_DELIVERY_DIMS: frozenset[DimensionName] = frozenset(
    [DimensionName.SCOPE, DimensionName.ESTIMATION]
)


def weighted_score(
    results: list[DimensionResult],
    weights: dict[DimensionName, float],
) -> tuple[float, dict[DimensionName, float]]:
    """Return ``(score, effective_weights)`` over the available dimensions.

    How redistribution works (FR-7): suppose Test Readiness (weight 0.30) is
    unavailable and Scope (0.25), Environment (0.20), Dependency (0.15), and
    Estimation (0.10) are available. Their configured weights sum to 0.70.
    Each is divided by that sum to produce new weights that add up to 1.0
    (e.g. Scope becomes 0.25/0.70 ≈ 0.357). The final score is then the sum
    of each dimension's score multiplied by its new effective weight.
    """
    # Only dimensions whose tool calls succeeded contribute to the score.
    available = [r for r in results if r.available]
    if not available:
        return 0.0, {}

    # Pull the configured weight for each available dimension.
    configured = {r.dimension: weights.get(r.dimension, 0.0) for r in available}
    total = sum(configured.values())
    if total <= 0:
        # Degenerate: no configured weight on available dims — fall back to equal split.
        equal = 1.0 / len(available)
        effective = {dim: equal for dim in configured}
    else:
        # Normalize so the effective weights sum to exactly 1.0 (redistribution step).
        effective = {dim: w / total for dim, w in configured.items()}

    # Final score = sum of (dimension score × its effective weight).
    score = sum(r.score * effective[r.dimension] for r in available)
    return score, effective


def split_scores(
    results: list[DimensionResult],
    weights: dict[DimensionName, float],
) -> tuple[float | None, float | None]:
    """Compute ship-safety and delivery-performance sub-scores (ADR-0016 item 6).

    Ship-safety covers TEST_READINESS + ENVIRONMENT + DEPENDENCY — dimensions that
    directly gate safe deployment. Delivery-performance covers SCOPE + ESTIMATION —
    dimensions that reflect how well the programme was planned and executed.

    Each group is scored independently using the same weight-redistribution logic
    as ``weighted_score()``, so missing dims within a group are handled gracefully.
    Returns ``(ship_safety, delivery_performance)`` in the 0.0-1.0 range; either
    value is ``None`` when no available dimension exists in that group.
    """
    ship_results = [r for r in results if r.available and r.dimension in _SHIP_SAFETY_DIMS]
    delivery_results = [r for r in results if r.available and r.dimension in _DELIVERY_DIMS]

    ship_score: float | None
    delivery_score: float | None

    if ship_results:
        ship_score, _ = weighted_score(ship_results, weights)
    else:
        ship_score = None

    if delivery_results:
        delivery_score, _ = weighted_score(delivery_results, weights)
    else:
        delivery_score = None

    return ship_score, delivery_score
