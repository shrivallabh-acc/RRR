"""``OperabilityAssessor`` — deployment pipeline health and operational readiness (ADR-0016 item 7).

One of three assessors that supersede the old ``OperationalAssessor``. Weighted 0.07.

Score = pipeline_score × 0.6 + ops_readiness × 0.4, where:

  pipeline: green=1.0 / yellow=0.6 / red=0.0 / unknown=0.5
  ops_readiness: mean(runbook_complete_score, on_call_schedule_active_score)
                 complete/active=1.0, absent=0.0

A change-freeze window or red pipeline produces a CRITICAL risk factor (NO_GO cap).
Missing runbook or absent on-call schedule produces a MAJOR risk factor (CONDITIONAL cap).
Recent deployment failures produce a MINOR advisory signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, PipelineStatus, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.operability import OperabilityInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import OperabilitySourceReader

_PIPELINE_WEIGHT = 0.6
_READINESS_WEIGHT = 0.4

_PIPELINE_SCORE: dict[PipelineStatus, float] = {
    PipelineStatus.GREEN: 1.0,
    PipelineStatus.YELLOW: 0.6,
    PipelineStatus.RED: 0.0,
    # Unknown is scored conservatively — partial credit, reduced confidence.
    PipelineStatus.UNKNOWN: 0.5,
}

# Confidence is reduced when the pipeline status is unknown — result less trustworthy.
_CONFIDENCE_CAP_UNKNOWN = 0.75


class OperabilityAssessor(BaseAssessor):
    """Scores deployment pipeline health and operational readiness (ADR-0016 item 7)."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        operability_reader: OperabilitySourceReader,
    ) -> None:
        """Wire the operability source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = operability_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.OPERABILITY

    def _assess(self) -> DeterministicAssessment:
        """Compute the operability score from deployment and runbook data.

        Combines pipeline health (60%) with operational readiness (40%). A change
        freeze or red pipeline raises CRITICAL risks regardless of the numeric score
        — these are hard blockers (ADR-0013). A missing runbook or absent on-call
        schedule raises MAJOR risks (CONDITIONAL cap).
        """
        data: OperabilityInput = self.invoke_tool(self._reader)

        pipeline_score = _PIPELINE_SCORE[data.deployment_pipeline]
        # Ops readiness = mean of runbook and on-call coverage signals.
        runbook_score = 1.0 if data.runbook_complete else 0.0
        on_call_score = 1.0 if data.on_call_schedule_active else 0.0
        ops_readiness = (runbook_score + on_call_score) / 2.0
        score = _PIPELINE_WEIGHT * pipeline_score + _READINESS_WEIGHT * ops_readiness

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        # A change-freeze window is an absolute blocker regardless of pipeline state.
        if data.change_freeze:
            risks.append(
                RiskFactor(
                    description="Change freeze is active — release is blocked",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.OPERABILITY,
                )
            )

        if data.deployment_pipeline is PipelineStatus.RED:
            risks.append(
                RiskFactor(
                    description="Deployment pipeline is red — builds are failing",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.OPERABILITY,
                )
            )
        elif data.deployment_pipeline is PipelineStatus.YELLOW:
            risks.append(
                RiskFactor(
                    description="Deployment pipeline is yellow — intermittent failures",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OPERABILITY,
                )
            )

        if not data.runbook_complete:
            risks.append(
                RiskFactor(
                    description="Operational runbook is incomplete or missing",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OPERABILITY,
                )
            )

        if not data.on_call_schedule_active:
            risks.append(
                RiskFactor(
                    description="No active on-call schedule for the release window",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.OPERABILITY,
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
                    dimension=DimensionName.OPERABILITY,
                )
            )

        # Unknown pipeline status means the snapshot is incomplete — cap confidence.
        if data.deployment_pipeline is PipelineStatus.UNKNOWN:
            confidence_cap = _CONFIDENCE_CAP_UNKNOWN

        classification = self._classify(data)
        facts = [
            f"Pipeline: {data.deployment_pipeline.value}  "
            f"(score {pipeline_score:.2f})  ·  "
            f"Runbook: {'complete' if data.runbook_complete else 'incomplete'}  ·  "
            f"On-call: {'active' if data.on_call_schedule_active else 'absent'}  ·  "
            f"Change freeze: {data.change_freeze}  ·  "
            f"Recent failures: {data.recent_deployment_failures}"
        ]
        evidence = [
            self.build_evidence(
                "operability_score",
                round(score, 3),
                f"pipeline {pipeline_score:.2f}×{_PIPELINE_WEIGHT} + "
                f"ops_readiness {ops_readiness:.2f}×{_READINESS_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Operability {score * 100:.1f}%: "
            f"pipeline={data.deployment_pipeline.value}, "
            f"runbook={'ok' if data.runbook_complete else 'missing'}, "
            f"on_call={'active' if data.on_call_schedule_active else 'absent'}, "
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
    def _classify(data: OperabilityInput) -> str:
        """Map pipeline, runbook, and on-call state to an operability classification.

        A red pipeline or active change freeze makes the release not ready regardless
        of other signals. Yellow pipeline or missing runbook/on-call is amber (at_risk).
        Green pipeline with complete runbook and active on-call is ready.
        """
        if data.change_freeze or data.deployment_pipeline is PipelineStatus.RED:
            return "not_ready"
        if (
            data.deployment_pipeline is PipelineStatus.YELLOW
            or data.deployment_pipeline is PipelineStatus.UNKNOWN
            or not data.runbook_complete
            or not data.on_call_schedule_active
        ):
            return "at_risk"
        return "ready"
