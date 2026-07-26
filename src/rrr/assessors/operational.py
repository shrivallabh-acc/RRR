"""``OperationalAssessor`` — deployment pipeline health + rollback readiness (ADR-0016).

Score = 0.6 × pipeline_score + 0.4 × rollback_score, where:

  pipeline: green=1.0 / yellow=0.6 / red=0.0 / unknown=0.5
  rollback: documented=1.0 / partial=0.5 / none=0.0 / unknown=0.5

A change-freeze window or a red pipeline immediately produces a CRITICAL risk
factor, which the GateEngine translates to a NO_GO verdict cap (ADR-0013).
A missing rollback plan produces a MAJOR risk (CONDITIONAL cap).
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, PipelineStatus, RiskSeverity, RollbackStatus
from rrr.models.evidence import RiskFactor
from rrr.models.operational import OperationalInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import OperationalSourceReader

# Scoring weights within this dimension (pipeline health matters more than rollback docs).
_PIPELINE_WEIGHT = 0.6
_ROLLBACK_WEIGHT = 0.4

_PIPELINE_SCORE: dict[PipelineStatus, float] = {
    PipelineStatus.GREEN: 1.0,
    PipelineStatus.YELLOW: 0.6,
    PipelineStatus.RED: 0.0,
    # Unknown is scored conservatively at 0.5 — partial credit, reduced confidence.
    PipelineStatus.UNKNOWN: 0.5,
}

_ROLLBACK_SCORE: dict[RollbackStatus, float] = {
    RollbackStatus.DOCUMENTED: 1.0,
    RollbackStatus.PARTIAL: 0.5,
    RollbackStatus.NONE: 0.0,
    # Unknown is scored conservatively at 0.5 — partial credit, reduced confidence.
    RollbackStatus.UNKNOWN: 0.5,
}

# Confidence is reduced when key fields are unknown — the assessor can score but
# the result is less trustworthy than a fully populated snapshot.
_CONFIDENCE_CAP_UNKNOWN = 0.75


class OperationalAssessor(BaseAssessor):
    """Scores deployment pipeline health and rollback readiness (ADR-0016)."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        operational_reader: OperationalSourceReader,
    ) -> None:
        """Wire the operational source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = operational_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.OPERATIONAL

    def _assess(self) -> DeterministicAssessment:
        """Compute the operational-readiness score from the deployment data.

        Combines pipeline health (60%) with rollback readiness (40%). A change
        freeze or red pipeline raises CRITICAL risks regardless of the numeric
        score — these are hard blockers (ADR-0013).
        """
        data: OperationalInput = self.invoke_tool(self._reader)

        pipeline_score = _PIPELINE_SCORE[data.deployment_pipeline]
        rollback_score = _ROLLBACK_SCORE[data.rollback_plan]
        score = _PIPELINE_WEIGHT * pipeline_score + _ROLLBACK_WEIGHT * rollback_score

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        # A change-freeze window is an absolute blocker regardless of pipeline state.
        if data.change_freeze:
            risks.append(
                RiskFactor(
                    description="Change freeze is active — release is blocked",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.OPERATIONAL,
                )
            )

        if data.deployment_pipeline is PipelineStatus.RED:
            risks.append(
                RiskFactor(
                    description="Deployment pipeline is red — builds are failing",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.OPERATIONAL,
                )
            )
        elif data.deployment_pipeline is PipelineStatus.YELLOW:
            risks.append(
                RiskFactor(
                    description="Deployment pipeline is yellow — intermittent failures",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OPERATIONAL,
                )
            )

        if data.rollback_plan is RollbackStatus.NONE:
            risks.append(
                RiskFactor(
                    description=(
                        "No rollback plan documented — deployment cannot be safely reversed"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OPERATIONAL,
                )
            )

        if data.recent_deployment_failures > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.recent_deployment_failures} deployment failure(s)"
                        " in the last 30 days"
                    ),
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.OPERATIONAL,
                )
            )

        # Unknown values mean the snapshot is incomplete — cap confidence to signal lower trust.
        if (
            data.deployment_pipeline is PipelineStatus.UNKNOWN
            or data.rollback_plan is RollbackStatus.UNKNOWN
        ):
            confidence_cap = _CONFIDENCE_CAP_UNKNOWN

        classification = self._classify(data)
        facts = [
            f"Pipeline: {data.deployment_pipeline.value}  "
            f"(score {pipeline_score:.2f})  ·  "
            f"Rollback: {data.rollback_plan.value}  "
            f"(score {rollback_score:.2f})  ·  "
            f"Change freeze: {data.change_freeze}  ·  "
            f"Recent failures: {data.recent_deployment_failures}"
        ]
        evidence = [
            self.build_evidence(
                "operational_score",
                round(score, 3),
                f"pipeline {pipeline_score:.2f}×{_PIPELINE_WEIGHT} + "
                f"rollback {rollback_score:.2f}×{_ROLLBACK_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Operational readiness {score * 100:.1f}%: "
            f"pipeline={data.deployment_pipeline.value}, "
            f"rollback={data.rollback_plan.value}, "
            f"freeze={data.change_freeze}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["ready", "at_risk", "not_ready"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: OperationalInput) -> str:
        """Map pipeline + rollback state to an overall operational classification.

        A red pipeline or active change freeze makes the release not ready even if
        rollback is documented. Yellow pipeline or partial rollback is amber.
        Green pipeline with documented rollback and no freeze is ready.
        """
        if data.change_freeze or data.deployment_pipeline is PipelineStatus.RED:
            return "not_ready"
        if (
            data.deployment_pipeline is PipelineStatus.YELLOW
            or data.rollback_plan in (RollbackStatus.PARTIAL, RollbackStatus.NONE)
            or data.deployment_pipeline is PipelineStatus.UNKNOWN
            or data.rollback_plan is RollbackStatus.UNKNOWN
        ):
            return "at_risk"
        return "ready"
