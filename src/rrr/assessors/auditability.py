"""``AuditabilityAssessor`` — audit trail completeness gate (ADR-0016 item 9).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score = mean of boolean field scores, with GDPR compliance weighted double
(0.0 = disabled/failed, 0.5 = unknown/None, 1.0 = enabled/passed).

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.auditability import AuditabilityInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import AuditabilitySourceReader

# Reduced confidence when key review fields are None (pending) — less evidence.
_CONFIDENCE_CAP_INCOMPLETE = 0.70


def _bool_score(value: bool | None) -> float:
    """Convert a bool or None to a 0–1 numeric score.

    True = full credit, None = uncertain (half credit), False = no credit.
    This avoids penalising unknown status as hard failure while not rewarding it.
    """
    if value is True:
        return 1.0
    if value is None:
        return 0.5
    return 0.0


class AuditabilityAssessor(BaseAssessor):
    """Gates release on audit-trail completeness and compliance (ADR-0016 item 9).

    CRITICAL risks veto the verdict to NO_GO when logging is disabled entirely
    or PII access is not captured — these are regulatory non-negotiables.
    MAJOR risks cap to CONDITIONAL for GDPR non-compliance or an untested trail.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        auditability_reader: AuditabilitySourceReader,
    ) -> None:
        """Wire the auditability source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = auditability_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.AUDITABILITY

    def _assess(self) -> DeterministicAssessment:
        """Compute audit-trail posture from logging configuration and compliance evidence.

        CRITICAL risks (→ NO_GO): audit logging disabled or PII access not logged.
        MAJOR risks (→ CONDITIONAL): GDPR compliance not confirmed or trail untested.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: AuditabilityInput = self.invoke_tool(self._reader)

        # Weighted mean: GDPR compliance counts double given its regulatory importance.
        components = [
            _bool_score(data.audit_logging_enabled),
            _bool_score(data.regulated_events_logged),
            _bool_score(data.audit_log_immutability_guaranteed),
            _bool_score(data.pii_access_logged),
            _bool_score(data.audit_trail_tested),
            _bool_score(data.gdpr_logging_compliant),
            _bool_score(data.gdpr_logging_compliant),  # double-weighted
        ]
        score = sum(components) / len(components)

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if not data.audit_logging_enabled:
            risks.append(
                RiskFactor(
                    description=(
                        "Audit logging is disabled — regulated transactions are not captured"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.AUDITABILITY,
                )
            )

        if not data.pii_access_logged:
            risks.append(
                RiskFactor(
                    description=(
                        "PII access events are not logged — data access by unauthorised "
                        "parties cannot be detected or investigated"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.AUDITABILITY,
                )
            )

        if data.gdpr_logging_compliant is False:
            risks.append(
                RiskFactor(
                    description=(
                        "Audit log design does not meet GDPR data-minimisation or "
                        "right-to-erasure requirements"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.AUDITABILITY,
                )
            )

        if not data.audit_trail_tested:
            risks.append(
                RiskFactor(
                    description=(
                        "Audit trail has not been validated end-to-end — completeness "
                        "and correctness are unverified"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.AUDITABILITY,
                )
            )

        # Pending GDPR review reduces confidence — review may reveal further issues.
        if data.gdpr_logging_compliant is None:
            confidence_cap = _CONFIDENCE_CAP_INCOMPLETE

        classification = self._classify(data)
        facts = [
            f"Logging enabled: {data.audit_logging_enabled}  ·  "
            f"Regulated events logged: {data.regulated_events_logged}  ·  "
            f"PII access logged: {data.pii_access_logged}  ·  "
            f"Immutability: {data.audit_log_immutability_guaranteed}  ·  "
            f"GDPR compliant: {data.gdpr_logging_compliant}  ·  "
            f"Trail tested: {data.audit_trail_tested}  ·  "
            f"Retention (days): {data.data_retention_days}"
        ]
        evidence = [
            self.build_evidence(
                "auditability_score",
                round(score, 3),
                "mean of 7 boolean components (GDPR double-weighted)",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Auditability posture {score * 100:.1f}%: "
            f"logging={data.audit_logging_enabled}, pii_logged={data.pii_access_logged}, "
            f"gdpr={data.gdpr_logging_compliant}, tested={data.audit_trail_tested}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["compliant", "at_risk", "non_compliant"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: AuditabilityInput) -> str:
        """Map logging state and compliance results to an auditability classification.

        ``non_compliant`` when logging is off or PII is not captured.
        ``at_risk`` when GDPR review is pending or trail is untested.
        ``compliant`` when all critical controls are confirmed and trail is tested.
        """
        if not data.audit_logging_enabled or not data.pii_access_logged:
            return "non_compliant"
        if data.gdpr_logging_compliant is not True or not data.audit_trail_tested:
            return "at_risk"
        return "compliant"
