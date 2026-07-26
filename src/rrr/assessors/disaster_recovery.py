"""``DisasterRecoveryAssessor`` — DR plan and test evidence gate (ADR-0016 item 10).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score formula:
  plan_score  = 1.0 if dr_plan_exists else 0.0
  test_score  = 1.0 if failover_tested, 0.5 if plan exists but untested, 0.0 if no plan
  rto_score   = 1.0 if rto_tested <= rto_target, else 0.0 (1.0 if targets not defined)
  rpo_score   = 1.0 if rpo_tested <= rpo_target, else 0.0 (1.0 if targets not defined)
  score = 0.3×plan_score + 0.3×test_score + 0.2×rto_score + 0.2×rpo_score

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from datetime import date

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.disaster_recovery import DisasterRecoveryInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import DisasterRecoverySourceReader

_PLAN_WEIGHT = 0.30
_TEST_WEIGHT = 0.30
_RTO_WEIGHT = 0.20
_RPO_WEIGHT = 0.20


class DisasterRecoveryAssessor(BaseAssessor):
    """Gates release on disaster recovery plan completeness and test evidence (ADR-0016 item 10).

    CRITICAL risks veto the verdict to NO_GO when there is no DR plan, failover
    has never been tested, or tested RTO/RPO values exceed their targets — these
    indicate the team cannot recover within agreed SLAs in a real disaster.
    MAJOR risks cap to CONDITIONAL when backup integrity is unverified or the
    last DR test is older than the configured staleness threshold.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        dr_reader: DisasterRecoverySourceReader,
    ) -> None:
        """Wire the disaster recovery source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = dr_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.DISASTER_RECOVERY

    def _assess(self) -> DeterministicAssessment:
        """Compute DR posture from plan existence, test evidence, and RTO/RPO adherence.

        CRITICAL risks (→ NO_GO): no DR plan, failover untested, or tested RTO/RPO
            exceeds the agreed target.
        MAJOR risks (→ CONDITIONAL): backup unverified or DR test is stale
            (older than ``dr_test_max_age_days`` days).

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: DisasterRecoveryInput = self.invoke_tool(self._reader)

        plan_score = 1.0 if data.dr_plan_exists else 0.0
        test_score = (
            1.0 if data.failover_tested else (0.5 if data.dr_plan_exists else 0.0)
        )

        # RTO/RPO: only penalise when both target and tested are defined and breach.
        rto_score = 1.0
        if data.rto_target_minutes is not None and data.rto_tested_minutes is not None:
            rto_score = 1.0 if data.rto_tested_minutes <= data.rto_target_minutes else 0.0

        rpo_score = 1.0
        if data.rpo_target_minutes is not None and data.rpo_tested_minutes is not None:
            rpo_score = 1.0 if data.rpo_tested_minutes <= data.rpo_target_minutes else 0.0

        score = (
            _PLAN_WEIGHT * plan_score
            + _TEST_WEIGHT * test_score
            + _RTO_WEIGHT * rto_score
            + _RPO_WEIGHT * rpo_score
        )

        risks: list[RiskFactor] = []

        if not data.dr_plan_exists:
            risks.append(
                RiskFactor(
                    description="No documented disaster recovery plan — recovery path is undefined",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DISASTER_RECOVERY,
                )
            )

        if not data.failover_tested:
            risks.append(
                RiskFactor(
                    description=(
                        "Failover sequence has never been exercised — "
                        "recovery capability is unproven under real conditions"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DISASTER_RECOVERY,
                )
            )

        if rto_score == 0.0:
            risks.append(
                RiskFactor(
                    description=(
                        f"Tested RTO {data.rto_tested_minutes} min exceeds target "
                        f"{data.rto_target_minutes} min — recovery takes longer than agreed SLA"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DISASTER_RECOVERY,
                )
            )

        if rpo_score == 0.0:
            risks.append(
                RiskFactor(
                    description=(
                        f"Tested RPO {data.rpo_tested_minutes} min exceeds target "
                        f"{data.rpo_target_minutes} min — data loss window exceeds agreed SLA"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DISASTER_RECOVERY,
                )
            )

        if not data.data_backup_verified:
            risks.append(
                RiskFactor(
                    description=(
                        "Backup integrity and restorability have not been verified — "
                        "restore capability is unconfirmed"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.DISASTER_RECOVERY,
                )
            )

        # Check DR test staleness when a test date is recorded.
        if data.dr_last_tested_date is not None:
            try:
                last_tested = date.fromisoformat(data.dr_last_tested_date)
                age_days = (date.today() - last_tested).days
                if age_days > data.dr_test_max_age_days:
                    risks.append(
                        RiskFactor(
                            description=(
                                f"DR test is {age_days} days old — older than the "
                                f"{data.dr_test_max_age_days}-day staleness threshold"
                            ),
                            severity=RiskSeverity.MAJOR,
                            dimension=DimensionName.DISASTER_RECOVERY,
                        )
                    )
            except ValueError:
                # Unparseable date — treat as stale rather than silently ignoring.
                risks.append(
                    RiskFactor(
                        description=(
                            f"DR last tested date {data.dr_last_tested_date!r} "
                            "could not be parsed as ISO 8601 — treating as stale"
                        ),
                        severity=RiskSeverity.MAJOR,
                        dimension=DimensionName.DISASTER_RECOVERY,
                    )
                )

        classification = self._classify(data, rto_score, rpo_score)
        rto_str = (
            f"{data.rto_tested_minutes}/{data.rto_target_minutes} min"
            if data.rto_tested_minutes is not None and data.rto_target_minutes is not None
            else "not measured"
        )
        rpo_str = (
            f"{data.rpo_tested_minutes}/{data.rpo_target_minutes} min"
            if data.rpo_tested_minutes is not None and data.rpo_target_minutes is not None
            else "not measured"
        )
        facts = [
            f"DR plan: {data.dr_plan_exists}  ·  "
            f"Failover tested: {data.failover_tested}  ·  "
            f"Backup verified: {data.data_backup_verified}  ·  "
            f"Last tested: {data.dr_last_tested_date or 'never'}  ·  "
            f"RTO tested/target: {rto_str}  ·  "
            f"RPO tested/target: {rpo_str}"
        ]
        evidence = [
            self.build_evidence(
                "dr_score",
                round(score, 3),
                f"plan {plan_score:.1f}×{_PLAN_WEIGHT} + test {test_score:.1f}×{_TEST_WEIGHT} "
                f"+ rto {rto_score:.1f}×{_RTO_WEIGHT} + rpo {rpo_score:.1f}×{_RPO_WEIGHT}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Disaster recovery posture {score * 100:.1f}%: "
            f"plan={data.dr_plan_exists}, failover_tested={data.failover_tested}, "
            f"backup_verified={data.data_backup_verified}."
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
    def _classify(
        data: DisasterRecoveryInput, rto_score: float, rpo_score: float
    ) -> str:
        """Map DR posture to a classification.

        ``not_ready`` when no plan, failover untested, or RTO/RPO targets breached.
        ``at_risk`` when backup unverified or test is stale.
        ``ready`` when plan exists, failover tested, backup verified, targets met.
        """
        if (
            not data.dr_plan_exists
            or not data.failover_tested
            or rto_score == 0.0
            or rpo_score == 0.0
        ):
            return "not_ready"
        if not data.data_backup_verified:
            return "at_risk"
        return "ready"
