"""``ScopeAssessor`` — story-point completion + scope-creep detection (FR-1, ADR-0012).

Deterministic core:

* **Score** = completion ratio ``closed / total`` from the latest snapshot's release
  ``summary`` (clamped 0-1).
* **Classification** — Delivered (>=0.90) / Partially Delivered (>=0.50) /
  Not Delivered (<0.50).
* **Velocity** (``weekly_last3``) is narrative context only, not part of the score.
* **Scope creep** — planned-SP growth from the earliest to the latest snapshot; if it
  exceeds ``scope_creep_threshold`` (default 0.10) a risk factor is raised that trips
  the CONDITIONAL gate (ADR-0013).

All reasoning/prose is delegated to the provider; the score stays here (ADR-0009).
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, RiskSeverity, ScopeClass
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.brain_reader import PlannedSPPoint, RKTBrainReader
from rrr.tools.runner import ToolRunner

DELIVERED_THRESHOLD = 0.90
PARTIAL_THRESHOLD = 0.50


class ScopeAssessor(BaseAssessor):
    """Scores release scope from the brain extract."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        brain_reader: RKTBrainReader,
        *,
        value_stream: str,
        snapshot: str = "latest",
        ir_name: str | None = None,
        scope_creep_threshold: float = 0.10,
    ) -> None:
        super().__init__(runner, provider)
        self._reader = brain_reader
        self._value_stream = value_stream
        self._snapshot = snapshot
        self._ir_name = ir_name
        self._scope_creep_threshold = scope_creep_threshold

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.SCOPE

    def _assess(self) -> DeterministicAssessment:
        """Compute the scope-delivery score from the RKT brain snapshot.

        Reads planned vs closed story points for the release iteration, derives
        a completion ratio, and classifies it as DELIVERED/PARTIALLY/NOT_DELIVERED.
        Scope creep (added SP exceeding the configured threshold) triggers a
        MAJOR risk factor even if overall completion looks acceptable.
        """
        result = self.invoke_tool(
            self._reader,
            value_stream=self._value_stream,
            snapshot=self._snapshot,
            ir_name=self._ir_name,
        )
        summary = result.release.summary
        completion = summary.closed / summary.total if summary.total else 0.0
        completion = max(0.0, min(1.0, completion))
        classification = self._classify(completion)

        facts: list[str] = []
        risks: list[RiskFactor] = []
        evidence = [
            self.build_evidence(
                "scope_completion",
                round(completion, 4),
                f"{summary.closed}/{summary.total} story points closed",
                tool=self._reader.name,
            )
        ]

        velocity = [p.value for p in result.release.weekly_last3]
        if velocity:
            trend = "rising" if velocity[-1] >= velocity[0] else "falling"
            facts.append(f"Velocity {trend} over last {len(velocity)} weeks ({velocity}).")
            evidence.append(
                self.build_evidence(
                    "velocity_last3", str(velocity), "weekly closed SP", tool=self._reader.name
                )
            )

        creep = self._scope_creep(result.planned_sp_history)
        if creep is not None and creep > self._scope_creep_threshold:
            pct = round(creep * 100, 1)
            threshold_pct = self._scope_creep_threshold * 100
            risks.append(
                RiskFactor(
                    description=(
                        f"Planned scope grew {pct}% across snapshots "
                        f"(> {threshold_pct:.0f}% threshold)"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.SCOPE,
                )
            )
            facts.append(f"Scope creep: planned SP +{pct}% baseline→latest.")
            evidence.append(
                self.build_evidence(
                    "scope_creep_pct", pct, "planned-SP growth", tool=self._reader.name
                )
            )

        label = classification.value.replace("_", " ")
        summary_line = (
            f"{summary.closed} of {summary.total} story points closed "
            f"({completion * 100:.1f}%) — {label}."
        )
        return DeterministicAssessment(
            score=completion,
            classification=classification.value,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=[c.value for c in ScopeClass],
        )

    @staticmethod
    def _classify(completion: float) -> ScopeClass:
        """Map a 0-1 completion ratio to a delivery class.

        DELIVERED means 90 %+ of planned story points are closed — good enough to
        ship. PARTIALLY_DELIVERED is the amber zone (50-90 %). NOT_DELIVERED means
        fewer than half the points are done — a release would be very high risk.
        Thresholds are module-level constants so they are easy to find and change.
        """
        if completion >= DELIVERED_THRESHOLD:
            return ScopeClass.DELIVERED
        if completion >= PARTIAL_THRESHOLD:
            return ScopeClass.PARTIALLY_DELIVERED
        return ScopeClass.NOT_DELIVERED

    @staticmethod
    def _scope_creep(history: list[PlannedSPPoint]) -> float | None:
        """Planned-SP growth ratio from the earliest to the latest snapshot, or None."""
        if len(history) < 2:
            return None
        baseline = history[0].total
        if baseline <= 0:
            return None
        return (history[-1].total - baseline) / baseline
