"""``DependencyRiskAssessor`` — software supply-chain risk gate (ADR-0016 item 13).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Distinct from ``DependencyAssessor`` (internal programme delivery) — this gate
covers third-party supply-chain integrity: CVEs in transitive dependencies,
malicious packages, supply-chain policy violations, and pinning.

Score:
  1.0 − critical_cve_penalty − malicious_penalty − violation_penalty − high_cve_penalty
  capped to [0, 1]. Informational only; risk factors drive the verdict.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.dependency_risk import DependencyRiskInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import DependencyRiskSourceReader

_CRITICAL_CVE_PENALTY = 0.25
_MALICIOUS_PENALTY = 1.0      # any malicious package zeroes the score
_VIOLATION_PENALTY = 0.15
_HIGH_CVE_PENALTY = 0.05
_HIGH_CVE_CAP = 0.30

# Reduced confidence when no SCA scan has been run.
_CONFIDENCE_CAP_NO_SCAN = 0.65


class DependencyRiskAssessor(BaseAssessor):
    """Gates release on software supply-chain risk (ADR-0016 item 13).

    Malicious packages and critical transitive CVEs are CRITICAL — they represent
    active security threats that must be resolved before shipping. Supply-chain
    policy violations and high transitive CVEs above threshold are MAJOR, indicating
    significant risk that may be mitigable but cannot be ignored.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        dep_risk_reader: DependencyRiskSourceReader,
    ) -> None:
        """Wire the dependency risk source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = dep_risk_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.DEPENDENCY_RISK

    def _assess(self) -> DeterministicAssessment:
        """Compute supply-chain risk from SCA scan results and policy violation counts.

        CRITICAL risks (→ NO_GO): malicious packages or critical transitive CVEs detected.
        MAJOR risks (→ CONDITIONAL): supply-chain policy violations or high transitive
            CVEs above the configured threshold.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: DependencyRiskInput = self.invoke_tool(self._reader)

        malicious_penalty = _MALICIOUS_PENALTY if data.known_malicious_packages > 0 else 0.0
        critical_penalty = min(data.critical_transitive_cves * _CRITICAL_CVE_PENALTY, 1.0)
        violation_penalty = min(data.supply_chain_violations * _VIOLATION_PENALTY, 0.60)
        excess_high = max(data.high_transitive_cves - data.high_transitive_cve_threshold, 0)
        high_penalty = min(excess_high * _HIGH_CVE_PENALTY, _HIGH_CVE_CAP)

        score = max(
            1.0 - malicious_penalty - critical_penalty - violation_penalty - high_penalty, 0.0
        )

        risks: list[RiskFactor] = []
        confidence_cap: float | None = None

        if data.known_malicious_packages > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.known_malicious_packages} malicious or typosquatted package(s) "
                        "detected in the dependency tree — immediate remediation required"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DEPENDENCY_RISK,
                )
            )

        if data.critical_transitive_cves > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.critical_transitive_cves} critical CVE(s) in transitive "
                        "dependencies — unpatched critical vulnerabilities in the supply chain"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.DEPENDENCY_RISK,
                )
            )

        if data.supply_chain_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.supply_chain_violations} supply-chain policy violation(s) — "
                        "unapproved sources, unsigned packages, or licence conflicts"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.DEPENDENCY_RISK,
                )
            )

        if data.high_transitive_cves > data.high_transitive_cve_threshold:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.high_transitive_cves} high-severity transitive CVE(s) "
                        f"≥ threshold ({data.high_transitive_cve_threshold})"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.DEPENDENCY_RISK,
                )
            )

        # No SCA scan means no evidence — reduce confidence significantly.
        if data.sca_scan_date is None:
            confidence_cap = _CONFIDENCE_CAP_NO_SCAN

        classification = self._classify(data)
        facts = [
            f"SCA tool: {data.sca_tool or 'not specified'}  ·  "
            f"Scan date: {data.sca_scan_date or 'never'}  ·  "
            f"Malicious packages: {data.known_malicious_packages}  ·  "
            f"Critical transitive CVEs: {data.critical_transitive_cves}  ·  "
            f"High transitive CVEs: {data.high_transitive_cves}  ·  "
            f"Supply-chain violations: {data.supply_chain_violations}  ·  "
            f"Pinned deps: {data.pinned_dependencies_pct:.0f}%"
        ]
        evidence = [
            self.build_evidence(
                "dependency_risk_score",
                round(score, 3),
                f"1.0 − malicious {malicious_penalty:.2f} − critical_cve {critical_penalty:.2f} "
                f"− violations {violation_penalty:.2f} − high_cve {high_penalty:.2f}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Dependency risk posture {score * 100:.1f}%: "
            f"malicious={data.known_malicious_packages}, "
            f"critical_cves={data.critical_transitive_cves}, "
            f"violations={data.supply_chain_violations}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["clean", "at_risk", "compromised"],
            confidence_cap=confidence_cap,
        )

    @staticmethod
    def _classify(data: DependencyRiskInput) -> str:
        """Map supply-chain risk signals to a classification.

        ``compromised`` when malicious packages or critical transitive CVEs are present.
        ``at_risk`` when supply-chain violations or high CVEs are above threshold.
        ``clean`` when no critical signals and scan was run.
        """
        if data.known_malicious_packages > 0 or data.critical_transitive_cves > 0:
            return "compromised"
        if (
            data.supply_chain_violations > 0
            or data.high_transitive_cves > data.high_transitive_cve_threshold
        ):
            return "at_risk"
        return "clean"
