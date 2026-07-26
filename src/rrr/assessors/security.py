"""``SecurityComplianceAssessor`` — SAST/DAST scans, CVE exposure, governance approvals (ADR-0016).

Gate-only dimension: weight = 0 in the weighted score so it cannot be averaged away,
but its risk factors drive verdict caps through the GateEngine (ADR-0013).

Score = 0.5 × sast_score + 0.5 × dast_score − cve_penalty (clamped to [0, 1]).
The score is informational; the CRITICAL and MAJOR risk factors are the blocking signal.

  sast/dast: passed=1.0 / not_run=0.5 / failed=0.0
  cve_penalty: each critical CVE −0.20 (capped at 0.60); each high CVE above
               the config threshold contributes −0.05 (capped at 0.30 total).
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.config.schema import SecurityAssessorConfig
from rrr.models.enums import DastStatus, DimensionName, RiskSeverity, SastStatus
from rrr.models.evidence import RiskFactor
from rrr.models.security import SecurityInput
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import SecuritySourceReader

_SAST_SCORE: dict[SastStatus, float] = {
    SastStatus.PASSED: 1.0,
    # Not running SAST is uncertain — penalised but not a hard zero.
    SastStatus.NOT_RUN: 0.5,
    SastStatus.FAILED: 0.0,
}

_DAST_SCORE: dict[DastStatus, float] = {
    DastStatus.PASSED: 1.0,
    # Not running DAST is uncertain — penalised but not a hard zero.
    DastStatus.NOT_RUN: 0.5,
    DastStatus.FAILED: 0.0,
}

# Critical CVE penalty per vuln (capped so one vuln cannot zero the score alone).
_CRITICAL_CVE_PENALTY = 0.20
_CRITICAL_CVE_CAP = 0.60

# High CVE penalty per vuln above threshold (softer than critical).
_HIGH_CVE_PENALTY = 0.05
_HIGH_CVE_CAP = 0.30

# Confidence is reduced when scan status is unknown (not_run) — result is less trustworthy.
_CONFIDENCE_CAP_UNKNOWN = 0.75


class SecurityComplianceAssessor(BaseAssessor):
    """Gates release on security scan results, CVE exposure, and governance approvals (ADR-0016).

    This dimension is gate-only (weight = 0 in WeightsConfig). It contributes no
    points to the weighted average but can veto a verdict to NO_GO or CONDITIONAL
    via the GateEngine when CRITICAL or MAJOR risk factors are raised (ADR-0013).
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        security_reader: SecuritySourceReader,
        security_config: SecurityAssessorConfig,
    ) -> None:
        """Wire the security source reader and assessor config into the assessor."""
        super().__init__(runner, provider)
        self._reader = security_reader
        self._config = security_config

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.SECURITY

    def _assess(self) -> DeterministicAssessment:
        """Compute security posture from scan results, CVEs, and governance approvals.

        CRITICAL risks (→ NO_GO cap via GateEngine): SAST failed, DAST failed,
        any open critical CVEs, data-privacy approval missing or rejected.
        MAJOR risks (→ CONDITIONAL cap): open high CVEs ≥ threshold, licence not approved.
        MINOR risk: pen test not yet run (advisory signal, no cap).

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: SecurityInput = self.invoke_tool(self._reader)

        sast_score = _SAST_SCORE[data.sast_status]
        dast_score = _DAST_SCORE[data.dast_status]

        # CVE penalties — capped so one category cannot dominate alone.
        critical_penalty = min(data.open_critical_cves * _CRITICAL_CVE_PENALTY, _CRITICAL_CVE_CAP)
        excess_high = max(data.open_high_cves - self._config.high_cve_threshold, 0)
        high_penalty = min(excess_high * _HIGH_CVE_PENALTY, _HIGH_CVE_CAP)

        score = max(0.5 * sast_score + 0.5 * dast_score - critical_penalty - high_penalty, 0.0)

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.sast_status is SastStatus.FAILED:
            risks.append(
                RiskFactor(
                    description="SAST scan failed — static security vulnerabilities detected",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.dast_status is DastStatus.FAILED:
            risks.append(
                RiskFactor(
                    description="DAST scan failed — dynamic runtime vulnerabilities detected",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.open_critical_cves > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.open_critical_cves} open critical CVE(s) — "
                        "unpatched critical vulnerabilities present"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.data_privacy_approved is False:
            risks.append(
                RiskFactor(
                    description="Data-privacy / GDPR impact assessment has not been approved",
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.open_high_cves >= self._config.high_cve_threshold:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.open_high_cves} open high-severity CVE(s) "
                        f"≥ threshold ({self._config.high_cve_threshold})"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.license_approved is False:
            risks.append(
                RiskFactor(
                    description="Dependency licence review has not been approved",
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.SECURITY,
                )
            )

        if data.pen_test_passed is False:
            risks.append(
                RiskFactor(
                    description="Penetration test completed but did not pass",
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.SECURITY,
                )
            )
        elif data.pen_test_passed is None:
            risks.append(
                RiskFactor(
                    description="Penetration test has not been run for this release",
                    severity=RiskSeverity.MINOR,
                    dimension=DimensionName.SECURITY,
                )
            )

        # Unknown scan status (not_run) means incomplete evidence — reduce confidence.
        if data.sast_status is SastStatus.NOT_RUN or data.dast_status is DastStatus.NOT_RUN:
            confidence_cap = _CONFIDENCE_CAP_UNKNOWN

        classification = self._classify(data)
        facts = [
            f"SAST: {data.sast_status.value}  ·  "
            f"DAST: {data.dast_status.value}  ·  "
            f"Critical CVEs: {data.open_critical_cves}  ·  "
            f"High CVEs: {data.open_high_cves}  ·  "
            f"Licence approved: {data.license_approved}  ·  "
            f"Privacy approved: {data.data_privacy_approved}  ·  "
            f"Pen-test: {data.pen_test_passed}"
        ]
        evidence = [
            self.build_evidence(
                "security_score",
                round(score, 3),
                f"sast {sast_score:.2f}×0.5 + dast {dast_score:.2f}×0.5 "
                f"− crit_penalty {critical_penalty:.2f} − high_penalty {high_penalty:.2f}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Security posture {score * 100:.1f}%: "
            f"sast={data.sast_status.value}, "
            f"dast={data.dast_status.value}, "
            f"critical_cves={data.open_critical_cves}, "
            f"high_cves={data.open_high_cves}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["clear", "at_risk", "failed"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: SecurityInput) -> str:
        """Map scan results and approvals to an overall security classification.

        Failed scans or open critical CVEs make the release failed regardless of
        other fields. Incomplete scans (not_run) or missing approvals are at_risk.
        All scans passed with zero critical CVEs and approvals in place is clear.
        """
        if (
            data.sast_status is SastStatus.FAILED
            or data.dast_status is DastStatus.FAILED
            or data.open_critical_cves > 0
            or data.data_privacy_approved is False
        ):
            return "failed"
        if (
            data.sast_status is SastStatus.NOT_RUN
            or data.dast_status is DastStatus.NOT_RUN
            or data.license_approved is False
            or data.license_approved is None
            or data.data_privacy_approved is None
        ):
            return "at_risk"
        return "clear"
