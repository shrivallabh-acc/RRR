"""Orchestration — fan out the five assessors, fuse scores, derive the verdict.

Parallel fan-out/fan-in (FR-6) via ``Orchestrator`` or the LangGraph
``StateGraph`` wrapper (``run_assessment_graph``, ADR-0002). Score = weighted sum
with weight redistribution for unavailable dimensions (FR-7); verdict = score band
capped by ADR-0013 veto/cap gates, INCOMPLETE if fewer than ``minimum_assessors``
available (FR-8). The provider synthesizes rationale + remediation; the verdict
*label* derives from the deterministic score/gates, not provider text (FR-22).

The scoring/verdict engine is framework-independent — ``run_assessment_graph``
wraps it in a LangGraph StateGraph when langgraph is installed, or falls back to
``Orchestrator.run()`` transparently when it is not (ADR-0002).
"""

from __future__ import annotations

from rrr.orchestration.graph import run_assessment_graph
from rrr.orchestration.orchestrator import Orchestrator
from rrr.orchestration.scoring import split_scores, weighted_score
from rrr.orchestration.trends import compute_trends
from rrr.orchestration.verdict import (
    derive_verdict,
    most_restrictive,
    score_band,
    triggered_caps,
)

__all__ = [
    "Orchestrator",
    "run_assessment_graph",
    "weighted_score",
    "split_scores",
    "derive_verdict",
    "score_band",
    "triggered_caps",
    "most_restrictive",
    "compute_trends",
]
