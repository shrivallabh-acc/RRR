"""Per-dimension trend comparison vs the previous assessment (FR-9).

For each dimension assessed in both the current and previous run, the delta drives
a direction: Δ > improving_delta → improving, Δ < degrading_delta → degrading,
else stable (thresholds from ``trend`` config). No previous assessment → no trends.
"""

from __future__ import annotations

from rrr.config.schema import TrendConfig
from rrr.models.assessment import AssessmentOutputModel, TrendData
from rrr.models.enums import TrendDirection


def compute_trends(
    current: AssessmentOutputModel,
    previous: AssessmentOutputModel | None,
    trend: TrendConfig,
) -> list[TrendData]:
    """Return per-dimension trends of ``current`` vs ``previous``.

    A trend entry is only produced when both assessments have a valid score for
    the same dimension. If a dimension was unavailable in either run it is skipped
    rather than reporting a misleading delta. The delta thresholds come from
    config (``trend.improving_delta`` / ``trend.degrading_delta``) so the team
    can tune what counts as "meaningfully better or worse" for their programme.
    """
    # Nothing to compare if there is no prior assessment.
    if previous is None:
        return []

    # Build a quick lookup: dimension → previous score (available dims only).
    prev_scores = {d.dimension: d.score for d in previous.dimensions if d.available}

    trends: list[TrendData] = []
    for dim in current.dimensions:
        # Skip this dimension if unavailable now, or if we have no prior data for it.
        if not dim.available or dim.dimension not in prev_scores:
            continue
        prior = prev_scores[dim.dimension]
        delta = dim.score - prior
        # Classify direction: positive delta → improving; negative → degrading; else stable.
        if delta > trend.improving_delta:
            direction = TrendDirection.IMPROVING
        elif delta < trend.degrading_delta:
            direction = TrendDirection.DEGRADING
        else:
            direction = TrendDirection.STABLE
        trends.append(
            TrendData(
                dimension=dim.dimension,
                previous_score=prior,
                current_score=dim.score,
                delta=round(delta, 4),
                direction=direction,
            )
        )
    return trends
