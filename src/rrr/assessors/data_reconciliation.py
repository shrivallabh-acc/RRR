"""``DataReconciliationAssessor`` — data migration integrity gate (ADR-0016 item 11).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

When ``migration_applicable`` is False the assessor returns a clean pass (score=1.0,
no risks) — the gate is a no-op for releases without a data migration.

Score (when migration is applicable):
  reconciliation_run × (1 − discrepancy_penalty) × approval_factor
  discrepancy_penalty: 1.0 if any discrepancies, else 0.0
  approval_factor: 1.0 if approved, 0.5 if pending, 0.0 if reconciliation not run

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.data_reconciliation import DataReconciliationInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import DataReconciliationSourceReader


class DataReconciliationAssessor(BaseAssessor):
    """Gates release on data migration integrity when a migration is applicable (ADR-0016 item 11).

    The gate is a no-op when ``migration_applicable`` is False — the assessor
    passes cleanly without raising risks. When a migration is present, any
    unreconciled discrepancy is CRITICAL; missing approval is MAJOR.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        reconciliation_reader: DataReconciliationSourceReader,
    ) -> None:
        """Wire the data reconciliation source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = reconciliation_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.DATA_RECONCILIATION

    def _assess(self) -> DeterministicAssessment:
        """Compute data migration integrity posture from reconciliation evidence.

        Short-circuits to a clean pass when no migration is in scope.
        CRITICAL risks (→ NO_GO): reconciliation not run or discrepancies found.
        MAJOR risks (→ CONDITIONAL): reconciliation not approved by data owner.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: DataReconciliationInput = self.invoke_tool(self._reader)

        # Migration not applicable — gate is a no-op; return clean immediately.
        if not data.migration_applicable:
            return DeterministicAssessment(
                score=1.0,
                classification="not_applicable",
                summary="No data migration in this release — reconciliation gate skipped.",
                facts=["migration_applicable: false"],
                risk_factors=[],
                evidence=[
                    self.build_evidence(
                        "reconciliation_score",
                        1.0,
                        "migration not applicable",
                        tool=self._reader.name,
                    )
                ],
                allowed_classifications=["not_applicable", "reconciled", "at_risk", "discrepancy"],
            )

        risks: list[RiskFactor] = []

        if not data.reconciliation_run:
            risks.append(
                RiskFactor(
                    description=(
                        "Data reconciliation has not been run after migration — "
                        "migrated record integrity is unverified"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DATA_RECONCILIATION,
                )
            )
            score = 0.0
        else:
            score = 1.0
            if data.discrepancy_count > 0:
                risks.append(
                    RiskFactor(
                        description=(
                            f"{data.discrepancy_count} record(s) ({data.discrepancy_pct:.2f}%) "
                            "could not be reconciled between source and target"
                        ),
                        severity=RiskSeverity.CRITICAL,
                        dimension=DimensionName.DATA_RECONCILIATION,
                    )
                )
                score = 0.0

            if data.reconciliation_approved is False:
                risks.append(
                    RiskFactor(
                        description=(
                            "Reconciliation report has been reviewed but the data "
                            "owner / DBA has not approved it"
                        ),
                        severity=RiskSeverity.MAJOR,
                        dimension=DimensionName.DATA_RECONCILIATION,
                    )
                )
                # Partial credit when approved explicitly rejected; still zero if discrepancies.
                score = max(score * 0.5, 0.0)
            elif data.reconciliation_approved is None:
                # Pending approval — partial confidence reduction only.
                score = max(score * 0.75, 0.0)

        classification = self._classify(data)
        pre = data.pre_migration_record_count
        post = data.post_migration_record_count
        count_str = f"{pre} → {post}" if pre is not None and post is not None else "not captured"
        facts = [
            f"Migration applicable: {data.migration_applicable}  ·  "
            f"Reconciliation run: {data.reconciliation_run}  ·  "
            f"Discrepancies: {data.discrepancy_count} ({data.discrepancy_pct:.2f}%)  ·  "
            f"Record count: {count_str}  ·  "
            f"Approved: {data.reconciliation_approved}"
        ]
        evidence = [
            self.build_evidence(
                "reconciliation_score",
                round(score, 3),
                f"run={data.reconciliation_run}, discrepancies={data.discrepancy_count}, "
                f"approved={data.reconciliation_approved}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Data reconciliation posture {score * 100:.1f}%: "
            f"run={data.reconciliation_run}, discrepancies={data.discrepancy_count}, "
            f"approved={data.reconciliation_approved}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["not_applicable", "reconciled", "at_risk", "discrepancy"],
        )

    @staticmethod
    def _classify(data: DataReconciliationInput) -> str:
        """Map reconciliation state to a classification.

        ``not_applicable`` when no migration is in scope.
        ``discrepancy`` when reconciliation was run but discrepancies were found.
        ``at_risk`` when reconciliation not run or approval pending.
        ``reconciled`` when run, zero discrepancies, and approved.
        """
        if not data.migration_applicable:
            return "not_applicable"
        if not data.reconciliation_run or data.discrepancy_count > 0:
            return "discrepancy" if data.reconciliation_run else "at_risk"
        if data.reconciliation_approved is not True:
            return "at_risk"
        return "reconciled"
