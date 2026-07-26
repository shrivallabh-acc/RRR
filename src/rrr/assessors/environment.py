"""``EnvironmentAssessor`` — provisioning score + stability-driven risk (FR-3).

* **Score** = average of per-component provisioning scores
  (validated 1.0 / configured 0.75 / provisioned 0.5 / missing 0.0).
* **Stability drives risk, not the score** (FR-3): a ``validated`` component that is
  ``down`` still scores 1.0 but raises a *critical* risk. Risks map to the ADR-0013
  gates — ``down`` → NO_GO, ``degraded`` or ``missing`` provisioning → CONDITIONAL.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, ProvisioningStatus, RiskSeverity, StabilityStatus
from rrr.models.environment import ComponentStatus, EnvironmentInput
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import EnvironmentSourceReader

PROVISIONING_SCORE = {
    ProvisioningStatus.VALIDATED: 1.0,
    ProvisioningStatus.CONFIGURED: 0.75,
    ProvisioningStatus.PROVISIONED: 0.5,
    ProvisioningStatus.MISSING: 0.0,
}


class EnvironmentAssessor(BaseAssessor):
    """Scores environment readiness from an environment source."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        env_reader: EnvironmentSourceReader,
    ) -> None:
        super().__init__(runner, provider)
        self._reader = env_reader

    @property
    def dimension(self) -> DimensionName:
        return DimensionName.ENVIRONMENT

    def _assess(self) -> DeterministicAssessment:
        """Compute the environment-readiness score from the provisioning source data.

        Averages the per-component provisioning scores across all components in
        the environment, then emits risk factors for any component that is down,
        degraded, or not yet provisioned.
        """
        env: EnvironmentInput = self.invoke_tool(self._reader)
        components = env.components
        score = sum(PROVISIONING_SCORE[c.provisioning] for c in components) / len(components)

        risks: list[RiskFactor] = []
        for c in components:
            if c.stability is StabilityStatus.DOWN:
                risks.append(
                    self._risk(f"{c.name} is down", RiskSeverity.CRITICAL, gate="environment_down")
                )
            elif c.stability is StabilityStatus.DEGRADED:
                risks.append(
                    self._risk(
                        f"{c.name} is degraded",
                        RiskSeverity.MAJOR,
                        gate="environment_degraded",
                    )
                )
            if c.provisioning is ProvisioningStatus.MISSING:
                risks.append(
                    self._risk(
                        f"{c.name} provisioning is missing",
                        RiskSeverity.MAJOR,
                        gate="environment_degraded",
                    )
                )

        classification = self._classify(components)
        down = sum(1 for c in components if c.stability is StabilityStatus.DOWN)
        degraded = sum(1 for c in components if c.stability is StabilityStatus.DEGRADED)
        facts = [
            f"{len(components)} components; avg provisioning {score:.2f}; "
            f"{down} down, {degraded} degraded."
        ]
        evidence = [
            self.build_evidence(
                "environment_score",
                round(score, 3),
                f"avg of {len(components)} component provisioning scores",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Environment provisioning {score * 100:.1f}% across "
            f"{len(components)} components — {classification}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["ready", "at_risk", "not_ready"],
        )

    def _risk(
        self, description: str, severity: RiskSeverity, *, gate: str | None = None
    ) -> RiskFactor:
        """Create an environment risk factor, pinning it to this dimension.

        The optional ``gate`` name links the risk to a named entry in ``GatesConfig``
        so the GateEngine can look up the correct verdict cap from config rather than
        inferring it from severity alone (ADR-0014).
        """
        return RiskFactor(
            description=description,
            severity=severity,
            dimension=DimensionName.ENVIRONMENT,
            gate=gate,
        )

    @staticmethod
    def _classify(components: list[ComponentStatus]) -> str:
        """Classify the environment as a whole based on the worst component state.

        Even one DOWN component makes the environment not ready for release — the
        system cannot be tested or deployed reliably. Any DEGRADED component or
        missing provisioning puts the environment in the amber (at_risk) zone.
        If all components are stable and fully provisioned we call it ready.
        """
        if any(c.stability is StabilityStatus.DOWN for c in components):
            return "not_ready"
        if any(
            c.stability is StabilityStatus.DEGRADED or c.provisioning is ProvisioningStatus.MISSING
            for c in components
        ):
            return "at_risk"
        return "ready"
