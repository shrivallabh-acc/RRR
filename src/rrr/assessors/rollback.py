"""``RollbackAssessor`` — rollback plan completeness and test evidence (ADR-0016 item 7).

Gate-only dimension (weight = 0): the score is informational; the CRITICAL and MAJOR
risk factors are the blocking signal that the GateEngine converts to verdict caps.

Score = plan_score × 0.6 + test_evidence_score × 0.4, where:
  plan: documented=1.0 / partial=0.5 / unknown=0.3 / none=0.0
  test_evidence: tested=1.0 / not_tested=0.0

Gate logic (ADR-0016 item 7):
  rollback_plan=none → CRITICAL (→ NO_GO)
  rollback_plan=partial or rollback_tested=False → MAJOR (→ CONDITIONAL)
  data_rollback_applicable=True and data_rollback_plan_exists=False → CRITICAL (→ NO_GO)
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, RiskSeverity, RollbackStatus
from rrr.models.evidence import RiskFactor
from rrr.models.rollback import RollbackInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import RollbackSourceReader

_PLAN_WEIGHT = 0.6
_TEST_WEIGHT = 0.4

_PLAN_SCORE: dict[RollbackStatus, float] = {
    RollbackStatus.DOCUMENTED: 1.0,
    RollbackStatus.PARTIAL: 0.5,
    # Unknown is scored conservatively — partial credit; reduces confidence.
    RollbackStatus.UNKNOWN: 0.3,
    RollbackStatus.NONE: 0.0,
}

# Confidence capped when plan is unknown — can't trust the result.
_CONFIDENCE_CAP_UNKNOWN = 0.70


class RollbackAssessor(BaseAssessor):
    """Gates on rollback plan existence and test evidence (ADR-0016 item 7, gate-only weight=0)."""

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        rollback_reader: RollbackSourceReader,
    ) -> None:
        """Wire the rollback source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = rollback_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.ROLLBACK

    def _assess(self) -> DeterministicAssessment:
        """Compute the rollback readiness score and emit gate risk factors.

        A missing rollback plan is CRITICAL — no deployment can be safely reversed.
        A partial plan or untested plan is MAJOR. A missing data-rollback plan
        when data_rollback_applicable=True is also CRITICAL (data integrity risk).
        Score weight is zero; only the gate risks matter for the verdict.
        """
        data: RollbackInput = self.invoke_tool(self._reader)

        plan_score = _PLAN_SCORE[data.rollback_plan]
        test_score = 1.0 if data.rollback_tested else 0.0
        score = _PLAN_WEIGHT * plan_score + _TEST_WEIGHT * test_score

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.rollback_plan is RollbackStatus.NONE:
            risks.append(
                RiskFactor(
                    description=(
                        "No rollback plan documented"
                        " — deployment cannot be safely reversed"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ROLLBACK,
                )
            )
        elif data.rollback_plan is RollbackStatus.PARTIAL:
            risks.append(
                RiskFactor(
                    description="Rollback plan is partial — recovery steps are incomplete",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ROLLBACK,
                )
            )

        if data.rollback_plan is not RollbackStatus.NONE and not data.rollback_tested:
            risks.append(
                RiskFactor(
                    description=(
                        "Rollback procedure has not been tested"
                        " in a non-production environment"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ROLLBACK,
                )
            )

        # A data migration without a data-rollback plan is a critical data integrity risk.
        if data.data_rollback_applicable and data.data_rollback_plan_exists is False:
            risks.append(
                RiskFactor(
                    description=(
                        "Data migration included but no data rollback plan exists"
                        " — data integrity risk if deployment is reversed"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ROLLBACK,
                )
            )

        if data.rollback_plan is RollbackStatus.UNKNOWN:
            confidence_cap = _CONFIDENCE_CAP_UNKNOWN

        classification = self._classify(data)
        facts = [
            f"Plan: {data.rollback_plan.value}  (score {plan_score:.2f})  ·  "
            f"Tested: {data.rollback_tested}  (score {test_score:.2f})  ·  "
            f"Data rollback applicable: {data.data_rollback_applicable}  ·  "
            f"Automated: {data.automated_rollback_available}"
        ]
        evidence = [
            self.build_evidence(
                "rollback_score",
                round(score, 3),
                f"plan {plan_score:.2f}×{_PLAN_WEIGHT} + "
                f"test_evidence {test_score:.2f}×{_TEST_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Rollback {score * 100:.1f}%: "
            f"plan={data.rollback_plan.value}, "
            f"tested={data.rollback_tested}, "
            + (
                "data_rollback=n/a."
                if not data.data_rollback_applicable
                else f"data_rollback_plan={data.data_rollback_plan_exists}."
            )
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
    def _classify(data: RollbackInput) -> str:
        """Map rollback plan and test state to a readiness classification.

        Not ready: no plan or data migration with no data rollback plan.
        At risk: partial plan or untested plan.
        Ready: documented plan that has been tested.
        """
        if data.rollback_plan is RollbackStatus.NONE:
            return "not_ready"
        if data.data_rollback_applicable and data.data_rollback_plan_exists is False:
            return "not_ready"
        if data.rollback_plan is RollbackStatus.PARTIAL or not data.rollback_tested:
            return "at_risk"
        return "ready"
