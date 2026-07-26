"""``ArchitectureDriftAssessor`` — architecture baseline compliance gate (ADR-0016 item 16).

Gate-only dimension: weight = 0 so it cannot be averaged away, but its risk
factors drive verdict caps through the GateEngine (ADR-0013).

Score = (adr_compliance_pct / 100) × (1 − drift_score) × pattern_factor
  pattern_factor = 1.0 if no unapproved patterns, else max(0, 1 − unapproved/10)
  Banned technologies detected instantly sets score to 0 (CRITICAL).

The score is informational; CRITICAL and MAJOR risk factors are the blocking signal.
"""

from __future__ import annotations

from rrr.assessors.base import BaseAssessor, DeterministicAssessment
from rrr.models.architecture_drift import ArchitectureDriftInput
from rrr.models.enums import DimensionName, RiskSeverity
from rrr.models.evidence import RiskFactor
from rrr.providers.base import LLMProvider
from rrr.tools.runner import ToolRunner
from rrr.tools.source_reader import ArchitectureDriftSourceReader


class ArchitectureDriftAssessor(BaseAssessor):
    """Gates release on architecture baseline compliance (ADR-0016 item 16).

    Banned technologies in the codebase and ADR compliance below the threshold
    are CRITICAL — they indicate the system has diverged from fundamental
    architectural decisions in ways that may have security and compliance
    implications. Unapproved patterns and excessive drift are MAJOR.
    """

    def __init__(
        self,
        runner: ToolRunner,
        provider: LLMProvider,
        drift_reader: ArchitectureDriftSourceReader,
    ) -> None:
        """Wire the architecture drift source reader into the assessor."""
        super().__init__(runner, provider)
        self._reader = drift_reader

    @property
    def dimension(self) -> DimensionName:
        """Return the dimension this assessor covers."""
        return DimensionName.ARCHITECTURE_DRIFT

    def _assess(self) -> DeterministicAssessment:
        """Compute architecture drift from ADR compliance, banned technologies, and drift score.

        CRITICAL risks (→ NO_GO): banned technologies detected or ADR compliance
            below the configured threshold (default 80%).
        MAJOR risks (→ CONDITIONAL): unapproved patterns or drift score above threshold.

        Weight is 0 in WeightsConfig; score is informational only.
        """
        data: ArchitectureDriftInput = self.invoke_tool(self._reader)

        # Net violations after subtracting formally approved deviations.
        net_unapproved = max(data.unapproved_patterns - data.approved_deviations, 0)
        net_tech_violations = max(data.tech_standard_violations - data.approved_deviations, 0)

        compliance_score = data.adr_compliance_pct / 100.0
        pattern_factor = max(1.0 - net_unapproved / 10.0, 0.0)

        if data.banned_technologies_detected > 0:
            score = 0.0
        else:
            score = compliance_score * (1.0 - data.drift_score) * pattern_factor

        risks: list[RiskFactor] = []

        if data.banned_technologies_detected > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{data.banned_technologies_detected} banned technology/technologies "
                        "detected in the codebase — on the prohibited technology list"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ARCHITECTURE_DRIFT,
                )
            )

        if data.adr_compliance_pct < data.adr_compliance_threshold_pct:
            risks.append(
                RiskFactor(
                    description=(
                        f"ADR compliance {data.adr_compliance_pct:.1f}% is below the "
                        f"{data.adr_compliance_threshold_pct:.1f}% threshold — "
                        "key architectural decisions are not reflected in the codebase"
                    ),
                    severity=RiskSeverity.CRITICAL,
                    dimension=DimensionName.ARCHITECTURE_DRIFT,
                )
            )

        if net_unapproved > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{net_unapproved} unapproved architectural pattern(s) detected "
                        "(after subtracting approved deviations)"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ARCHITECTURE_DRIFT,
                )
            )

        if data.drift_score > data.drift_threshold:
            risks.append(
                RiskFactor(
                    description=(
                        f"Architecture drift score {data.drift_score:.2f} exceeds "
                        f"threshold {data.drift_threshold:.2f} — "
                        "codebase has significantly diverged from the approved baseline"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ARCHITECTURE_DRIFT,
                )
            )

        if net_tech_violations > 0:
            risks.append(
                RiskFactor(
                    description=(
                        f"{net_tech_violations} technology standard violation(s) — "
                        "deprecated or non-standard technologies in use"
                    ),
                    severity=RiskSeverity.MAJOR,
                    dimension=DimensionName.ARCHITECTURE_DRIFT,
                )
            )

        classification = self._classify(data, net_unapproved)
        facts = [
            f"Baseline: {data.baseline_version or 'not specified'}  ·  "
            f"ADR compliance: {data.adr_compliance_pct:.1f}%  ·  "
            f"Drift score: {data.drift_score:.2f}  ·  "
            f"Banned technologies: {data.banned_technologies_detected}  ·  "
            f"Unapproved patterns: {net_unapproved} (net)  ·  "
            f"Tech standard violations: {net_tech_violations} (net)"
        ]
        evidence = [
            self.build_evidence(
                "architecture_drift_score",
                round(score, 3),
                f"compliance {compliance_score:.2f} × (1−drift {data.drift_score:.2f}) "
                f"× pattern_factor {pattern_factor:.2f}",
                tool=self._reader.name,
            )
        ]
        summary_line = (
            f"Architecture drift posture {score * 100:.1f}%: "
            f"adr_compliance={data.adr_compliance_pct:.1f}%, "
            f"drift={data.drift_score:.2f}, "
            f"banned={data.banned_technologies_detected}."
        )
        return DeterministicAssessment(
            score=score,
            classification=classification,
            summary=summary_line,
            facts=facts,
            risk_factors=risks,
            evidence=evidence,
            allowed_classifications=["aligned", "drifting", "diverged"],
        )

    @staticmethod
    def _classify(data: ArchitectureDriftInput, net_unapproved: int) -> str:
        """Map drift signals to an architecture baseline compliance classification.

        ``diverged`` when banned technologies detected or ADR compliance is critically low.
        ``drifting`` when unapproved patterns exist or drift score is above threshold.
        ``aligned`` when fully compliant with the baseline and no violations.
        """
        if (
            data.banned_technologies_detected > 0
            or data.adr_compliance_pct < data.adr_compliance_threshold_pct
        ):
            return "diverged"
        if net_unapproved > 0 or data.drift_score > data.drift_threshold:
            return "drifting"
        return "aligned"
