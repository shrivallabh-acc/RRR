"""``ProductionReadinessAssessor`` — go-live readiness gate (ADR-0016 item 14).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score = mean of boolean readiness signals:
  capacity_confirmed, go_live_checklist_complete, release_comms_prepared,
  support_team_briefed, rollback_decision_criteria_defined,
  post_release_monitoring_plan, and each stakeholder_sign_off.

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.models.production_readiness import ProductionReadinessInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import ProductionReadinessSourceReader


class ProductionReadinessAssessor(BaseAssessor):
    """Gates release on go-live readiness checklist completion (ADR-0016 item 14).

    Unconfirmed capacity or an incomplete go-live checklist are CRITICAL — they
    indicate the team has not verified the system can handle production load, or
    that mandatory pre-launch steps are outstanding. Missing stakeholder sign-offs
    are MAJOR — the release has not been approved through the correct governance path.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        readiness_reader: ProductionReadinessSourceReader,
    ) -> None:
        """Wire the production readiness source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = readiness_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.PRODUCTION_READINESS

    def _assess(self) -> DeterministicAssessment:
        """Compute go-live readiness from checklist completion and sign-off status.

        CRITICAL risks (→ NO_GO): capacity unconfirmed or go-live checklist incomplete.
        MAJOR risks (→ CONDITIONAL): any required stakeholder sign-off is missing or declined.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: ProductionReadinessInput = self.invoke_tool(self._reader)

        risks: list[RiskFactor] = []

        if not data.capacity_confirmed:
            risks.append(
                RiskFactor(
                    description=(
                        "Production capacity has not been confirmed — system may be "
                        "under-provisioned for expected post-release load"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.PRODUCTION_READINESS,
                )
            )

        if not data.go_live_checklist_complete:
            risks.append(
                RiskFactor(
                    description=(
                        "Go-live checklist is not complete — mandatory pre-launch "
                        "steps are still outstanding"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.PRODUCTION_READINESS,
                )
            )

        # Raise MAJOR for every unsigned or declined stakeholder sign-off.
        for role, signed in data.stakeholder_sign_offs.items():
            if signed is not True:
                status = "declined" if signed is False else "pending"
                risks.append(
                    RiskFactor(
                        description=(
                            f"Stakeholder sign-off from '{role}' is {status} — "
                            "release has not been approved through the full governance path"
                        ),
                        severity=RiskSeverity.MAJOR,
                        dimension=DimensionName.PRODUCTION_READINESS,
                    )
                )

        # Compute score as mean of all binary readiness signals.
        booleans = [
            data.capacity_confirmed,
            data.go_live_checklist_complete,
            data.release_comms_prepared,
            data.support_team_briefed,
            data.rollback_decision_criteria_defined,
            data.post_release_monitoring_plan,
        ]
        # Feature flags: None means not applicable — treat as True (full credit).
        flags_score = 1.0 if data.feature_flags_configured is not False else 0.0
        booleans_score = sum(1.0 if b else 0.0 for b in booleans) / len(booleans)

        # Stakeholder sign-offs: each signed = 1.0, pending/declined = 0.0.
        sign_off_scores = [
            1.0 if v is True else 0.0 for v in data.stakeholder_sign_offs.values()
        ]
        sign_off_mean = sum(sign_off_scores) / len(sign_off_scores) if sign_off_scores else 1.0

        score = (booleans_score + flags_score + sign_off_mean) / 3.0

        classification = self._classify(data)
        signed_roles = [r for r, v in data.stakeholder_sign_offs.items() if v is True]
        pending_roles = [r for r, v in data.stakeholder_sign_offs.items() if v is not True]
        facts = [
            f"Capacity confirmed: {data.capacity_confirmed}  ·  "
            f"Checklist complete: {data.go_live_checklist_complete}  ·  "
            f"Comms prepared: {data.release_comms_prepared}  ·  "
            f"Support briefed: {data.support_team_briefed}  ·  "
            f"Rollback criteria: {data.rollback_decision_criteria_defined}  ·  "
            f"Monitoring plan: {data.post_release_monitoring_plan}",
            f"Sign-offs: {signed_roles or 'none'}  ·  Pending/declined: {pending_roles or 'none'}",
        ]
        evidence = [
            self.build_evidence(
                "production_readiness_score",
                round(score, 3),
                f"booleans {booleans_score:.2f} + flags {flags_score:.1f} "
                f"+ sign_offs {sign_off_mean:.2f} / 3",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Production readiness posture {score * 100:.1f}%: "
            f"capacity={data.capacity_confirmed}, "
            f"checklist={data.go_live_checklist_complete}, "
            f"sign_offs={len(signed_roles)}/{len(data.stakeholder_sign_offs)}."
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

    @staticmethod
    def _classify(data: ProductionReadinessInput) -> str:
        """Map go-live readiness signals to a classification.

        ``not_ready`` when capacity is unconfirmed or checklist is incomplete.
        ``at_risk`` when any stakeholder sign-off is missing.
        ``ready`` when all critical controls confirmed and all sign-offs obtained.
        """
        if not data.capacity_confirmed or not data.go_live_checklist_complete:
            return "not_ready"
        if any(v is not True for v in data.stakeholder_sign_offs.values()):
            return "at_risk"
        return "ready"
